from pathlib import Path

from generation.model_registry import list_model_specs
from generation.schemas import GenerationRequest


def test_registry_contains_all_supported_checkpoints() -> None:
    model_ids = {spec.model_id for spec in list_model_specs()}

    assert model_ids == {
        "mattergen_base",
        "mp_20_base",
        "dft_mag_density",
        "dft_mag_density_hhi_score",
        "chemical_system",
        "chemical_system_energy_above_hull",
        "dft_band_gap",
        "ml_bulk_modulus",
        "space_group",
    }


def test_request_resolves_models_from_conditions() -> None:
    cases = {
        "dft_mag_density": {"dft_mag_density": 0.15},
        "dft_mag_density_hhi_score": {
            "dft_mag_density": 0.2,
            "hhi_score": 0.3,
        },
        "chemical_system": {"chemical_system": "Nd-Fe-B"},
        "chemical_system_energy_above_hull": {
            "chemical_system": "Nd-Fe-B",
            "energy_above_hull": 0.05,
        },
        "dft_band_gap": {"dft_band_gap": 1.5},
        "ml_bulk_modulus": {"ml_bulk_modulus": 300},
        "space_group": {"space_group": 194},
    }

    for expected_model, conditions in cases.items():
        request = GenerationRequest(conditions=conditions)
        assert request.resolve_model_id() == expected_model
        assert request.normalized().conditions


def test_unconditional_model_accepts_empty_conditions() -> None:
    request = GenerationRequest(model_id="mattergen_base").normalized()

    assert request.model_id == "mattergen_base"
    assert request.conditions == {}


def test_registry_paths_are_under_vendored_mattergen() -> None:
    for spec in list_model_specs():
        assert spec.checkpoint_dir == (
            Path(__file__).resolve().parents[1]
            / "vendor"
            / "mattergen"
            / "checkpoints"
            / spec.model_id
        )
