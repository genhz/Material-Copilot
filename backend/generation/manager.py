"""Manage generation jobs and their worker subprocesses."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

from config import MatterGenConfig, get_mattergen_config
from generation.adapter import MatterGenAdapter
from generation.campaign_store import CampaignStore
from generation.events import RealtimeHub
from generation.exceptions import (
    GenerationDisabledError,
    GenerationError,
    InvalidJobStateError,
)
from generation.schemas import (
    CampaignCandidateCollection,
    CampaignCandidateGroup,
    CampaignJob,
    CandidateCollection,
    GenerationJob,
    GenerationRequest,
    ModelInfo,
    CampaignRequest,
    CampaignRunState,
)
from generation.store import GenerationStore, utc_now
from generation.model_registry import get_model_spec, list_model_specs


logger = logging.getLogger(__name__)


class GenerationManager:
    """Submit and monitor isolated MatterGen worker processes."""

    def __init__(self, config: MatterGenConfig):
        self.config = config
        self.store = GenerationStore(config.artifact_root)
        self.adapter = MatterGenAdapter(config)
        self.hub = RealtimeHub()
        self.campaign_store = CampaignStore(
            config.artifact_root.parent / "campaigns"
        )
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._tasks: set[asyncio.Task] = set()
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._cancel_requested: set[str] = set()
        self._campaign_cancel_requested: set[str] = set()
        self._campaign_tasks: set[asyncio.Task] = set()
        self._started = False

    async def startup(self) -> None:
        if self._started:
            return
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)
        self.store.mark_stale_running_jobs_failed()
        self.campaign_store.mark_stale_running_failed()
        self._started = True

    async def shutdown(self) -> None:
        for job_id, process in list(self._processes.items()):
            if process.returncode is None:
                self._cancel_requested.add(job_id)
                await self._terminate_process(process)
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._campaign_tasks:
            await asyncio.gather(
                *self._campaign_tasks, return_exceptions=True
            )
        self._tasks.clear()
        self._campaign_tasks.clear()
        self._processes.clear()
        self._started = False
        self._semaphore = None

    def _ensure_started(self) -> asyncio.Semaphore:
        if not self._started or self._semaphore is None:
            raise RuntimeError("GenerationManager 尚未启动")
        return self._semaphore

    async def submit(self, request: GenerationRequest) -> GenerationJob:
        if not self.config.enabled:
            raise GenerationDisabledError()

        self._ensure_started()
        try:
            normalized_request = request.normalized()
        except ValueError as exc:
            raise GenerationError(
                "INVALID_CONDITIONS",
                str(exc),
                status_code=422,
            ) from exc

        model_spec = get_model_spec(normalized_request.model_id or "")
        self.adapter.preflight(model_spec)
        job = self.store.create_job(
            normalized_request,
            model_id=model_spec.model_id,
            model_label=model_spec.display_name,
        )
        task = asyncio.create_task(self._run_job(job.job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def get_job(self, job_id: str) -> GenerationJob:
        return self.store.get_job(job_id)

    async def submit_campaign(
        self, request: CampaignRequest
    ) -> CampaignJob:
        if not self.config.enabled:
            raise GenerationDisabledError()
        self._ensure_started()

        runs: list[CampaignRunState] = []
        for run_request in request.runs:
            generation_request = GenerationRequest(
                model_id=run_request.model_id,
                conditions=run_request.conditions,
                num_candidates=run_request.num_candidates,
                guidance_scale=run_request.guidance_scale,
                seed=run_request.seed,
            )
            try:
                generation_request = generation_request.normalized()
            except ValueError as exc:
                raise GenerationError(
                    "INVALID_CONDITIONS",
                    str(exc),
                    status_code=422,
                ) from exc

            model_spec = get_model_spec(generation_request.model_id or "")
            self.adapter.preflight(model_spec)
            runs.append(
                CampaignRunState(
                    run_id=self.campaign_store.new_id(),
                    model_id=model_spec.model_id,
                    model_label=model_spec.display_name,
                    conditions=generation_request.conditions,
                    request=generation_request,
                )
            )

        campaign = CampaignJob(
            campaign_id=self.campaign_store.new_id(),
            name=request.name,
            runs=runs,
            created_at=utc_now(),
        )
        self.campaign_store.create(campaign)
        task = asyncio.create_task(self._run_campaign(campaign.campaign_id))
        self._campaign_tasks.add(task)
        task.add_done_callback(self._campaign_tasks.discard)
        return campaign

    async def get_campaign(self, campaign_id: str) -> CampaignJob:
        return self.campaign_store.get(campaign_id)

    async def get_campaign_candidates(
        self, campaign_id: str
    ) -> CampaignCandidateCollection:
        campaign = self.campaign_store.get(campaign_id)
        groups: list[CampaignCandidateGroup] = []
        combined = []

        for run in campaign.runs:
            candidates = []
            if run.job_id:
                try:
                    candidates = self.store.get_candidates(run.job_id)
                except Exception:
                    candidates = []
            groups.append(
                CampaignCandidateGroup(
                    model_id=run.model_id,
                    model_label=run.model_label,
                    conditions=run.conditions,
                    candidates=candidates,
                )
            )
            combined.extend(candidates)

        return CampaignCandidateCollection(
            campaign_id=campaign_id,
            groups=groups,
            candidates=combined,
            total_count=len(combined),
        )

    async def cancel_campaign(self, campaign_id: str) -> CampaignJob:
        campaign = self.campaign_store.get(campaign_id)
        if campaign.status in {"completed", "failed", "cancelled", "partial"}:
            raise InvalidJobStateError(
                f"Campaign 处于终态，不能取消：{campaign.status}"
            )

        self._campaign_cancel_requested.add(campaign_id)
        for run in campaign.runs:
            if run.job_id:
                try:
                    await self.cancel(run.job_id)
                except GenerationError:
                    pass

        campaign = self.campaign_store.update(
            campaign_id,
            status="cancelled",
            completed_at=utc_now(),
        )
        await self._publish_campaign(campaign_id)
        return campaign

    async def get_candidates(self, job_id: str) -> CandidateCollection:
        job = self.store.get_job(job_id)
        if job.status != "completed":
            raise InvalidJobStateError("生成任务尚未完成，不能读取候选结构。")
        return self.store.get_candidate_collection(job_id)

    async def cancel(self, job_id: str) -> GenerationJob:
        job = self.store.get_job(job_id)
        if job.status in {"completed", "failed", "cancelled"}:
            raise InvalidJobStateError(
                f"生成任务处于终态，不能取消：{job.status}"
            )

        self._cancel_requested.add(job_id)
        job = self.store.update_job(
            job_id,
            status="cancelled",
            phase="cancelled",
            message="生成任务已取消。",
            completed_at=utc_now(),
            worker_pid=None,
        )
        await self._publish_job(job_id, event_type="update")

        process = self._processes.get(job_id)
        if process is not None and process.returncode is None:
            await self._terminate_process(process)
        return job

    def subscribe(self, channel: str, resource_id: str) -> asyncio.Queue:
        return self.hub.add_subscriber(channel, resource_id)

    def unsubscribe(
        self,
        channel: str,
        resource_id: str,
        queue: asyncio.Queue,
    ) -> None:
        self.hub.remove_subscriber(channel, resource_id, queue)

    async def available_models(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for spec in list_model_specs():
            available = False
            missing_reason = None
            if self.config.enabled:
                try:
                    self.adapter.preflight(spec)
                    available = True
                except GenerationError as exc:
                    missing_reason = exc.message

            models.append(
                ModelInfo(
                    model_id=spec.model_id,
                    display_name=spec.display_name,
                    description=spec.description,
                    category=spec.category,
                    available=available,
                    conditions={
                        name: condition.as_dict()
                        for name, condition in spec.conditions.items()
                    },
                    missing_reason=missing_reason,
                    download_url=(
                        spec.download_url if not available else None
                    ),
                )
            )
        return models

    async def _run_campaign(self, campaign_id: str) -> None:
        campaign = self.campaign_store.get(campaign_id)
        campaign = self.campaign_store.update(
            campaign_id,
            status="running",
        )
        await self._publish_campaign(campaign_id)

        total_runs = len(campaign.runs)
        completed_runs = 0
        failed_runs = 0

        for index, run in enumerate(campaign.runs):
            if campaign_id in self._campaign_cancel_requested:
                self._campaign_cancel_requested.discard(campaign_id)
                return

            job = await self.submit(run.request)
            campaign = self.campaign_store.get(campaign_id)
            runs = list(campaign.runs)
            runs[index] = runs[index].model_copy(
                update={"job_id": job.job_id, "status": "queued"}
            )
            campaign = self.campaign_store.update(
                campaign_id,
                runs=runs,
            )
            await self._publish_campaign(campaign_id)

            while True:
                if campaign_id in self._campaign_cancel_requested:
                    try:
                        await self.cancel(job.job_id)
                    except GenerationError:
                        pass
                    self._campaign_cancel_requested.discard(campaign_id)
                    return

                current = self.store.get_job(job.job_id)
                campaign = self.campaign_store.get(campaign_id)
                runs = list(campaign.runs)
                runs[index] = runs[index].model_copy(
                    update={
                        "status": current.status,
                        "progress": current.progress,
                        "error_message": current.error_message,
                    }
                )
                campaign_progress = (
                    index + current.progress
                ) / total_runs
                campaign = self.campaign_store.update(
                    campaign_id,
                    runs=runs,
                    progress=campaign_progress,
                )
                await self._publish_campaign(campaign_id)

                if current.status in {
                    "completed",
                    "failed",
                    "cancelled",
                }:
                    if current.status == "completed":
                        completed_runs += 1
                    else:
                        failed_runs += 1
                    break
                await asyncio.sleep(0.5)

        if failed_runs == 0:
            status = "completed"
        elif completed_runs > 0:
            status = "partial"
        else:
            status = "failed"

        self.campaign_store.update(
            campaign_id,
            status=status,
            progress=1.0,
            completed_at=utc_now(),
        )
        await self._publish_campaign(campaign_id)

    async def _publish_campaign(self, campaign_id: str) -> None:
        try:
            campaign = self.campaign_store.get(campaign_id)
        except Exception:
            return
        await self.hub.publish(
            "generation.campaign",
            campaign_id,
            {
                "type": "update",
                "channel": "generation.campaign",
                "resource_id": campaign_id,
                "campaign": campaign.model_dump(mode="json"),
            },
        )

    async def _run_job(self, job_id: str) -> None:
        semaphore = self._ensure_started()
        async with semaphore:
            if job_id in self._cancel_requested:
                self._cancel_requested.discard(job_id)
                return

            backend_root = Path(__file__).resolve().parents[1]
            environment = os.environ.copy()
            environment["PYTHONUNBUFFERED"] = "1"
            environment.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
            environment.setdefault(
                "PYTORCH_CUDA_ALLOC_CONF",
                self.config.cuda_alloc_conf,
            )
            python_path = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = (
                f"{backend_root}{os.pathsep}{python_path}"
                if python_path
                else str(backend_root)
            )

            stdout_path = self.store.stdout_path(job_id)
            stderr_path = self.store.stderr_path(job_id)
            stdout_handle = stdout_path.open("wb")
            stderr_handle = stderr_path.open("wb")

            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "generation.worker",
                    "--job-id",
                    job_id,
                    cwd=str(backend_root),
                    env=environment,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    start_new_session=True,
                )
                self._processes[job_id] = process
                stdout_handle.close()
                stderr_handle.close()
                watch_task = asyncio.create_task(
                    self._watch_job(job_id, process)
                )

                try:
                    return_code = await asyncio.wait_for(
                        process.wait(),
                        timeout=self.config.worker_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    await self._terminate_process(process)
                    self.store.update_job(
                        job_id,
                        status="failed",
                        phase="failed",
                        message="MatterGen 生成任务超时。",
                        error_code="GENERATION_TIMEOUT",
                        error_message="MatterGen 生成任务超时。",
                        completed_at=utc_now(),
                        worker_pid=None,
                    )
                    await self._publish_job(job_id, event_type="update")
                    return

                if job_id in self._cancel_requested:
                    self._cancel_requested.discard(job_id)
                    return

                await self._publish_job(job_id, event_type="update")

                current = self.store.get_job(job_id)
                if return_code != 0 and current.status not in {"failed", "cancelled"}:
                    self.store.update_job(
                        job_id,
                        status="failed",
                        phase="failed",
                        message=self._tail(stderr_path),
                        error_code="WORKER_FAILED",
                        error_message=self._tail(stderr_path),
                        completed_at=utc_now(),
                        worker_pid=None,
                    )
                    await self._publish_job(job_id, event_type="update")
                elif return_code == 0 and current.status == "running":
                    self.store.update_job(
                        job_id,
                        status="completed",
                        phase="completed",
                        progress=1.0,
                        message="生成任务已完成。",
                        completed_at=utc_now(),
                        worker_pid=None,
                    )
                    await self._publish_job(job_id, event_type="update")
            except Exception as exc:
                logger.exception("Unable to launch MatterGen worker")
                self.store.update_job(
                    job_id,
                    status="failed",
                    phase="failed",
                    message=str(exc),
                    error_code="WORKER_FAILED",
                    error_message=str(exc),
                    completed_at=utc_now(),
                    worker_pid=None,
                )
                await self._publish_job(job_id, event_type="update")
            finally:
                if "watch_task" in locals():
                    watch_task.cancel()
                    await asyncio.gather(watch_task, return_exceptions=True)
                if not stdout_handle.closed:
                    stdout_handle.close()
                if not stderr_handle.closed:
                    stderr_handle.close()
                self._processes.pop(job_id, None)

    async def _watch_job(
        self,
        job_id: str,
        process: asyncio.subprocess.Process,
    ) -> None:
        last_signature = None
        while True:
            try:
                job = self.store.get_job(job_id)
            except Exception:
                return

            signature = (
                job.status,
                job.phase,
                job.progress,
                job.message,
                job.sequence,
            )
            if signature != last_signature:
                await self.hub.publish(
                    "generation.job",
                    job_id,
                    {
                        "type": "update",
                        "channel": "generation.job",
                        "resource_id": job_id,
                        "job": job.model_dump(mode="json"),
                    },
                )
                last_signature = signature

            if job.status in {"completed", "failed", "cancelled"}:
                return

            if process.returncode is not None:
                await asyncio.sleep(0.1)
                if process.returncode is not None:
                    await self._publish_job(job_id, event_type="update")
                    return

            await asyncio.sleep(0.25)

    async def _publish_job(self, job_id: str, event_type: str) -> None:
        try:
            job = self.store.get_job(job_id)
        except Exception:
            return
        await self.hub.publish(
            "generation.job",
            job_id,
            {
                "type": event_type,
                "channel": "generation.job",
                "resource_id": job_id,
                "job": job.model_dump(mode="json"),
            },
        )

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return

        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            except Exception:
                process.kill()
            await process.wait()

    @staticmethod
    def _tail(path: Path, max_chars: int = 4000) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "Worker process failed without a readable error log."
        return text[-max_chars:] or "Worker process failed without an error message."


_manager: Optional[GenerationManager] = None


def get_generation_manager() -> GenerationManager:
    """Return the process-wide generation manager."""

    global _manager
    if _manager is None:
        _manager = GenerationManager(get_mattergen_config())
    return _manager
