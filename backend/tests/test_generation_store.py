from pathlib import Path

import pytest

from generation.exceptions import JobNotFoundError
from generation.schemas import (
    CandidateCollection,
    GeneratedCandidate,
    GenerationRequest,
)
from generation.store import GenerationStore


def test_store_round_trip(tmp_path: Path) -> None:
    store = GenerationStore(tmp_path)
    job = store.create_job(
        GenerationRequest(
            target_magnetic_density=0.15,
            num_candidates=2,
            guidance_scale=2.0,
            seed=42,
        ),
        model_id="dft_mag_density",
    )

    loaded = store.get_job(job.job_id)
    assert loaded.status == "queued"
    assert loaded.request.seed == 42

    running = store.update_job(job.job_id, status="running", progress=0.5)
    assert running.status == "running"
    assert store.get_job(job.job_id).progress == 0.5


def test_store_rejects_invalid_job_id(tmp_path: Path) -> None:
    store = GenerationStore(tmp_path)
    with pytest.raises(JobNotFoundError):
        store.job_dir("../../etc/passwd")


def test_store_candidate_round_trip(tmp_path: Path) -> None:
    store = GenerationStore(tmp_path)
    job = store.create_job(
        GenerationRequest(target_magnetic_density=0.1),
        model_id="dft_mag_density",
    )
    candidate = GeneratedCandidate(
        candidate_id=f"mg-{job.job_id}-000",
        material_id=f"mg-{job.job_id}-000",
        model_id="dft_mag_density",
        model_label="磁密度生成",
        formula="NaCl",
        pretty_formula="NaCl",
        cif="data_NaCl",
        density=2.16,
        formula_unit=2,
        elements=["Na", "Cl"],
    )

    store.save_candidate_collection(
        job.job_id,
        CandidateCollection(
            candidates=[candidate],
            total_count=1,
        ),
    )

    loaded = store.get_candidate_collection(job.job_id)
    assert loaded.total_count == 1
    assert loaded.candidates[0].formula == "NaCl"
