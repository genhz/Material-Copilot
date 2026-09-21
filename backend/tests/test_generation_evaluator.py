from pathlib import Path
from zipfile import ZipFile

from pymatgen.core import Lattice, Structure

from generation.evaluator import extract_candidates
from generation.model_registry import get_model_spec
from generation.schemas import GenerationRequest


def test_extract_candidates_reads_valid_cif(tmp_path: Path) -> None:
    structure = Structure(
        lattice=Lattice.cubic(4.0),
        species=["Na", "Cl"],
        coords=[[0, 0, 0], [0.5, 0.5, 0.5]],
    )
    archive_path = tmp_path / "generated_crystals_cif.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("gen_000.cif", structure.to(fmt="cif"))

    collection = extract_candidates(
        archive_path,
        job_id="00000000-0000-0000-0000-000000000001",
        request=GenerationRequest(target_magnetic_density=0.15),
        model_spec=get_model_spec("dft_mag_density"),
        candidates_dir=tmp_path / "candidates",
    )

    assert collection.total_count == 1
    assert collection.invalid_count == 0
    assert len(collection.candidates) == 1
    assert collection.candidates[0].elements == ["Na", "Cl"]
    assert collection.candidates[0].formula_unit == 2
    assert collection.candidates[0].cif


def test_extract_candidates_records_invalid_cif(tmp_path: Path) -> None:
    archive_path = tmp_path / "generated_crystals_cif.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("invalid.cif", "not a cif")

    collection = extract_candidates(
        archive_path,
        job_id="00000000-0000-0000-0000-000000000002",
        request=GenerationRequest(target_magnetic_density=0.15),
        model_spec=get_model_spec("dft_mag_density"),
        candidates_dir=tmp_path / "candidates",
    )

    assert collection.total_count == 1
    assert collection.invalid_count == 1
    assert collection.candidates == []
