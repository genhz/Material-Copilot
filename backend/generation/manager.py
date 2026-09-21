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
from generation.events import RealtimeHub
from generation.exceptions import (
    GenerationDisabledError,
    GenerationError,
    InvalidJobStateError,
)
from generation.schemas import (
    CandidateCollection,
    GenerationJob,
    GenerationRequest,
    ModelInfo,
)
from generation.store import GenerationStore, utc_now


logger = logging.getLogger(__name__)


class GenerationManager:
    """Submit and monitor isolated MatterGen worker processes."""

    def __init__(self, config: MatterGenConfig):
        self.config = config
        self.store = GenerationStore(config.artifact_root)
        self.adapter = MatterGenAdapter(config)
        self.hub = RealtimeHub()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._tasks: set[asyncio.Task] = set()
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._cancel_requested: set[str] = set()
        self._started = False

    async def startup(self) -> None:
        if self._started:
            return
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)
        self.store.mark_stale_running_jobs_failed()
        self._started = True

    async def shutdown(self) -> None:
        for job_id, process in list(self._processes.items()):
            if process.returncode is None:
                self._cancel_requested.add(job_id)
                await self._terminate_process(process)
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
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
        self.adapter.preflight()
        job = self.store.create_job(request, model_id=self.config.model_id)
        task = asyncio.create_task(self._run_job(job.job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def get_job(self, job_id: str) -> GenerationJob:
        return self.store.get_job(job_id)

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
        available = False
        if self.config.enabled:
            try:
                self.adapter.preflight()
                available = True
            except GenerationError:
                available = False

        return [
            ModelInfo(
                model_id=self.config.model_id,
                available=available,
                conditions=["dft_mag_density"],
            )
        ]

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
