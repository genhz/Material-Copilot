"""Convert MatterGen output archives into validated candidate structures."""

from __future__ import annotations

import math
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from generation.exceptions import GenerationError
from generation.model_registry import MatterGenModelSpec
from generation.schemas import (
    CandidateCollection,
    GeneratedCandidate,
    GenerationRequest,
)


def _structure_validation(structure: Structure) -> dict:
    lattice_values = structure.lattice.matrix.reshape(-1)
    coordinate_values = structure.cart_coords.reshape(-1)
    finite = bool(
        all(math.isfinite(float(value)) for value in lattice_values)
        and all(math.isfinite(float(value)) for value in coordinate_values)
    )
    return {
        "cif_parse": True,
        "finite": finite,
        "num_sites": len(structure),
    }


def _spacegroup_info(structure: Structure) -> tuple[str | None, int | None, str | None]:
    try:
        analyzer = SpacegroupAnalyzer(structure)
        symbol = analyzer.get_space_group_symbol()
        number = analyzer.get_space_group_number()
        crystal_system = analyzer.get_crystal_system()
        return symbol, number, crystal_system
    except Exception:
        return None, None, None


def _candidate_from_structure(
    structure: Structure,
    job_id: str,
    index: int,
    request: GenerationRequest,
    model_spec: MatterGenModelSpec,
) -> GeneratedCandidate:
    validation = _structure_validation(structure)
    if not validation["finite"]:
        raise ValueError("结构包含非有限晶格或坐标值")

    if len(structure) < 1:
        raise ValueError("结构不包含原子")

    spacegroup_symbol, spacegroup_number, crystal_system = _spacegroup_info(structure)
    candidate_id = f"mg-{job_id}-{index:03d}"

    return GeneratedCandidate(
        candidate_id=candidate_id,
        material_id=candidate_id,
        model_id=model_spec.model_id,
        model_label=model_spec.display_name,
        formula=structure.composition.reduced_formula,
        pretty_formula=structure.composition.reduced_formula,
        cif=structure.to(fmt="cif"),
        density=float(structure.density),
        formula_unit=len(structure),
        elements=[element.symbol for element in structure.composition.elements],
        generation_conditions={
            **request.conditions,
            "guidance_scale": request.guidance_scale,
            "seed": request.seed,
        },
        validation=validation,
        spacegroup_symbol=spacegroup_symbol,
        spacegroup_number=spacegroup_number,
        crystal_system=crystal_system,
    )


def extract_candidates(
    archive_path: Path,
    *,
    job_id: str,
    request: GenerationRequest,
    model_spec: MatterGenModelSpec,
    candidates_dir: Path,
) -> CandidateCollection:
    """Read a MatterGen CIF ZIP and return validated candidates."""

    if not archive_path.is_file():
        raise GenerationError(
            "INVALID_OUTPUT",
            f"MatterGen 未生成候选 ZIP：{archive_path}",
            status_code=500,
        )

    candidates: list[GeneratedCandidate] = []
    invalid_count = 0
    errors: list[str] = []
    candidates_dir.mkdir(parents=True, exist_ok=True)

    try:
        with ZipFile(archive_path) as archive:
            cif_names = sorted(
                name
                for name in archive.namelist()
                if name.lower().endswith(".cif") and not name.startswith("/")
            )
            for index, name in enumerate(cif_names):
                try:
                    cif_text = archive.read(name).decode("utf-8")
                    structure = Structure.from_str(cif_text, fmt="cif")
                    candidate = _candidate_from_structure(
                        structure,
                        job_id=job_id,
                        index=index,
                        request=request,
                        model_spec=model_spec,
                    )
                    candidates.append(candidate)
                    (candidates_dir / f"{index:03d}.cif").write_text(
                        candidate.cif,
                        encoding="utf-8",
                    )
                except Exception as exc:
                    invalid_count += 1
                    errors.append(f"{name}: {exc}")
    except (BadZipFile, OSError, UnicodeDecodeError) as exc:
        raise GenerationError(
            "INVALID_OUTPUT",
            f"无法读取 MatterGen 候选 ZIP：{exc}",
            status_code=500,
        ) from exc

    return CandidateCollection(
        candidates=candidates,
        invalid_count=invalid_count,
        total_count=len(cif_names),
        validation={
            "valid_count": len(candidates),
            "invalid_count": invalid_count,
            "errors": errors[:20],
        },
    )
