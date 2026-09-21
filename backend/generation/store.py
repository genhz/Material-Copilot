"""Filesystem-backed generation job store."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from generation.exceptions import JobNotFoundError
from generation.schemas import (
    CandidateCollection,
    GeneratedCandidate,
    GenerationJob,
    GenerationRequest,
)


JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class GenerationStore:
    """Store jobs and generated candidates on the local filesystem."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create_job(
        self,
        request: GenerationRequest,
        model_id: str,
        model_label: Optional[str] = None,
    ) -> GenerationJob:
        job_id = str(uuid.uuid4())
        job = GenerationJob(
            job_id=job_id,
            status="queued",
            phase="queued",
            progress=0.0,
            message="任务正在等待生成 Worker。",
            sequence=0,
            model_id=model_id,
            model_label=model_label,
            request=request,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.save_job(job)
        self.write_json(self.job_dir(job_id) / "request.json", request.model_dump(mode="json"))
        return job

    def get_job(self, job_id: str) -> GenerationJob:
        path = self.job_dir(job_id) / "job.json"
        if not path.is_file():
            raise JobNotFoundError(job_id)

        try:
            return GenerationJob.model_validate(self.read_json(path))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"生成任务状态文件损坏：{path}") from exc

    def save_job(self, job: GenerationJob) -> None:
        self.write_json(
            self.job_dir(job.job_id) / "job.json",
            job.model_dump(mode="json"),
        )

    def update_job(self, job_id: str, **updates: Any) -> GenerationJob:
        job = self.get_job(job_id)
        updates["sequence"] = job.sequence + 1
        updates["updated_at"] = utc_now()
        updated = job.model_copy(update=updates)
        self.save_job(updated)
        return updated

    def save_candidate_collection(
        self,
        job_id: str,
        collection: CandidateCollection,
    ) -> None:
        self.write_json(
            self.job_dir(job_id) / "candidates.json",
            collection.model_dump(mode="json"),
        )

    def get_candidate_collection(self, job_id: str) -> CandidateCollection:
        self.get_job(job_id)
        path = self.job_dir(job_id) / "candidates.json"
        if not path.is_file():
            return CandidateCollection()

        try:
            return CandidateCollection.model_validate(self.read_json(path))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"候选结构文件损坏：{path}") from exc

    def get_candidates(self, job_id: str) -> list[GeneratedCandidate]:
        return self.get_candidate_collection(job_id).candidates

    def job_dir(self, job_id: str) -> Path:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise JobNotFoundError(job_id)

        path = self.root / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def stdout_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "stdout.log"

    def stderr_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "stderr.log"

    def generated_zip_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "generated_crystals_cif.zip"

    def candidates_dir(self, job_id: str) -> Path:
        path = self.job_dir(job_id) / "candidates"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def mark_stale_running_jobs_failed(self) -> int:
        """Fail jobs left in running state after an API restart."""

        count = 0
        for job_file in self.root.glob("*/job.json"):
            try:
                job = GenerationJob.model_validate(self.read_json(job_file))
            except (ValidationError, ValueError, json.JSONDecodeError):
                continue

            if job.status in {"queued", "running"}:
                self.update_job(
                    job.job_id,
                    status="failed",
                    error_code="WORKER_INTERRUPTED",
                    error_message="后端服务重启，生成任务已中断。",
                    completed_at=utc_now(),
                )
                count += 1
        return count

    @staticmethod
    def write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    @staticmethod
    def read_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
