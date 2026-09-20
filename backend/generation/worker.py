"""Standalone MatterGen generation worker process."""

from __future__ import annotations

import argparse
import logging
import os
import traceback

from config import get_mattergen_config
from generation.adapter import MatterGenAdapter
from generation.evaluator import extract_candidates
from generation.exceptions import GenerationError
from generation.store import GenerationStore, utc_now


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def _update_progress(store: GenerationStore, job_id: str, progress: float) -> None:
    bounded = max(0.0, min(float(progress), 1.0))
    store.update_job(job_id, progress=bounded)


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
        progress=0.0,
        started_at=job.started_at or utc_now(),
        worker_pid=os.getpid(),
        error_code=None,
        error_message=None,
    )

    try:
        adapter = MatterGenAdapter(config)
        adapter.preflight()
        job_dir = store.job_dir(job_id)
        adapter.generate(
            request=job.request,
            output_dir=job_dir,
            progress_callback=lambda **values: _update_progress(
                store,
                job_id,
                values.get("progress", 0.0),
            ),
        )

        collection = extract_candidates(
            store.generated_zip_path(job_id),
            job_id=job_id,
            request=job.request,
            candidates_dir=store.candidates_dir(job_id),
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
            progress=1.0,
            completed_at=utc_now(),
            worker_pid=None,
        )
        return 0
    except GenerationError as exc:
        logger.exception("Generation job failed")
        store.update_job(
            job_id,
            status="failed",
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

