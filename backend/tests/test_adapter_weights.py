from dataclasses import replace
from pathlib import Path

import pytest

from config import get_mattergen_config
from generation.adapter import MatterGenAdapter
from generation.exceptions import GenerationError
from generation.model_registry import get_model_spec


def test_missing_model_weights_raise_download_guidance(tmp_path: Path) -> None:
    spec = replace(
        get_model_spec("dft_mag_density"),
        checkpoint_dir=tmp_path / "missing-model",
    )

    with pytest.raises(GenerationError) as exc_info:
        MatterGenAdapter(get_mattergen_config()).preflight(spec)

    assert exc_info.value.code == "MODEL_WEIGHTS_NOT_FOUND"
    assert str(spec.checkpoint_dir) in exc_info.value.message
