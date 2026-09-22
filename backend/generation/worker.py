"""Standalone MatterGen generation worker process."""

from __future__ import annotations

import argparse
import logging
import os
import time
import traceback

from config import get_mattergen_config
from generation.adapter import MatterGenAdapter
from generation.evaluator import extract_candidates
from generation.exceptions import GenerationError
from generation.model_registry import get_model_spec
from generation.store import GenerationStore, utc_now


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def _progress_reporter(store: GenerationStore, job_id: str):
    last_progress = -1.0
    last_write = 0.0

    def report(**values) -> None:
        nonlocal last_progress, last_write
        sampled = max(0.0, min(float(values.get("progress", 0.0)), 1.0))
        # Model loading occupies the first 5%, diffusion sampling the next 90%.
        progress = 0.05 + (0.90 * sampled)
        now = time.monotonic()
        if (
            progress < 1.0
            and progress - last_progress < 0.01
            and now - last_write < 1.0
        ):
            return

        last_progress = progress
        last_write = now
        store.update_job(
            job_id,
            status="running",
            phase="generating",
            progress=progress,
            message=f"扩散采样 {round(sampled * 100)}%",
        )

    return report


def run_job(job_id: str) -> int:
    """Run one generation job and persist its terminal state."""

    config = get_mattergen_config()
    store = GenerationStore(config.artifact_root)
    job = store.get_job(job_id)

    if job.status == "cancelled":
        return 0

    store.update_job(
        job_id,
        status="running",
        phase="loading_model",
        progress=0.0,
        message="正在加载 MatterGen 模型。",
        started_at=job.started_at or utc_now(),
        worker_pid=os.getpid(),
        error_code=None,
        error_message=None,
    )

    try:
        adapter = MatterGenAdapter(config)
        model_spec = get_model_spec(job.model_id)
        job_request = job.request.normalized()
        adapter.preflight(model_spec)
        job_dir = store.job_dir(job_id)
        report_progress = _progress_reporter(store, job_id)
        adapter.generate(
            request=job_request,
            model_spec=model_spec,
            output_dir=job_dir,
            progress_callback=report_progress,
        )

        store.update_job(
            job_id,
            status="running",
            phase="postprocessing",
            progress=0.96,
            message="正在解析和校验候选结构。",
        )

        collection = extract_candidates(
            store.generated_zip_path(job_id),
            job_id=job_id,
            request=job_request,
            model_spec=model_spec,
            candidates_dir=store.candidates_dir(job_id),
            max_candidates=job_request.num_candidates,
        )
        if not collection.candidates:
            raise GenerationError(
                "INVALID_OUTPUT",
                "MatterGen 未产生任何可解析的 CIF 候选。",
                status_code=500,
            )

        store.save_candidate_collection(job_id, collection)
        store.update_job(
            job_id,
            status="completed",
            phase="completed",
            progress=1.0,
            message=f"已生成 {len(collection.candidates)} 个有效候选。",
            completed_at=utc_now(),
            worker_pid=None,
        )
        return 0
    except GenerationError as exc:
        logger.exception("Generation job failed")
        store.update_job(
            job_id,
            status="failed",
            phase="failed",
            message=exc.message,
            error_code=exc.code,
            error_message=exc.message,
            completed_at=utc_now(),
            worker_pid=None,
        )
        return 1
    except Exception as exc:
        logger.exception("Unexpected generation worker failure")
        store.update_job(
            job_id,
            status="failed",
            phase="failed",
            message=str(exc),
            error_code="GENERATION_FAILED",
            error_message=str(exc),
            completed_at=utc_now(),
            worker_pid=None,
        )
        traceback.print_exc()
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one MatterGen generation job")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    return run_job(args.job_id)


if __name__ == "__main__":
    raise SystemExit(main())
