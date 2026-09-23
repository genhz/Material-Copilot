"""Registry of MatterGen checkpoints bundled with the backend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from generation.exceptions import GenerationError


ConditionType = Literal["float", "int", "string"]
CHECKPOINT_ROOT = (
    Path(__file__).resolve().parents[1]
    / "vendor"
    / "mattergen"
    / "checkpoints"
)


@dataclass(frozen=True)
class ConditionSpec:
    """Description and defaults for one model conditioning input."""

    name: str
    value_type: ConditionType
    required: bool
    default: float | int | str | None
    description: str
    minimum: float | None = None
    maximum: float | None = None
    options: tuple[str, ...] = ()
    unit: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.value_type,
            "required": self.required,
            "default": self.default,
            "description": self.description,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "options": list(self.options),
            "unit": self.unit,
        }


@dataclass(frozen=True)
class MatterGenModelSpec:
    """Metadata and checkpoint location for one MatterGen model."""

    model_id: str
    display_name: str
    description: str
    checkpoint_dir: Path
    conditions: dict[str, ConditionSpec]
    default_guidance_scale: float
    category: str
    task_types: tuple[str, ...] = ("material_generation",)
    objective_sets: tuple[frozenset[str], ...] = (frozenset(),)
    required_inputs: tuple[str, ...] = ()
    supports_composition: bool = False
    supports_exact_formula: bool = False
    supports_space_group: bool = False
    supports_crystal_system: bool = False
    postprocessors: tuple[str, ...] = ("element_composition_filter",)
    static_available: bool = True

    @property
    def download_url(self) -> str:
        return (
            "https://huggingface.co/microsoft/mattergen/resolve/main/"
            f"checkpoints/{self.model_id}/checkpoints/last.ckpt"
        )


def _float_condition(
    name: str,
    default: float,
    description: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    unit: str | None = None,
) -> ConditionSpec:
    return ConditionSpec(
        name=name,
        value_type="float",
        required=True,
        default=default,
        description=description,
        minimum=minimum,
        maximum=maximum,
        unit=unit,
    )


MODEL_REGISTRY: dict[str, MatterGenModelSpec] = {
    "mattergen_base": MatterGenModelSpec(
        model_id="mattergen_base",
        display_name="通用材料探索（Alex-MP-20）",
        description="无条件发现无机材料结构。",
        checkpoint_dir=CHECKPOINT_ROOT / "mattergen_base",
        conditions={},
        default_guidance_scale=0.0,
        category="unconditional",
        objective_sets=(frozenset(),),
    ),
    "mp_20_base": MatterGenModelSpec(
        model_id="mp_20_base",
        display_name="通用材料探索（MP-20）",
        description="在 MP-20 分布上无条件生成晶体结构。",
        checkpoint_dir=CHECKPOINT_ROOT / "mp_20_base",
        conditions={},
        default_guidance_scale=0.0,
        category="unconditional",
        objective_sets=(frozenset(),),
    ),
    "dft_mag_density": MatterGenModelSpec(
        model_id="dft_mag_density",
        display_name="磁密度生成",
        description="根据目标磁密度生成候选结构。",
        checkpoint_dir=CHECKPOINT_ROOT / "dft_mag_density",
        conditions={
            "dft_mag_density": _float_condition(
                "dft_mag_density",
                0.15,
                "目标 DFT 磁密度，单位 Å⁻³。",
                minimum=0.0,
                maximum=1.0,
                unit="Å^-3",
            )
        },
        default_guidance_scale=2.0,
        category="magnetic",
        objective_sets=(frozenset({"dft_mag_density"}),),
    ),
    "dft_mag_density_hhi_score": MatterGenModelSpec(
        model_id="dft_mag_density_hhi_score",
        display_name="磁密度与供应风险",
        description="联合约束磁密度和元素供应风险 HHI。",
        checkpoint_dir=CHECKPOINT_ROOT / "dft_mag_density_hhi_score",
        conditions={
            "dft_mag_density": _float_condition(
                "dft_mag_density",
                0.15,
                "目标 DFT 磁密度，单位 Å⁻³。",
                minimum=0.0,
                maximum=1.0,
                unit="Å^-3",
            ),
            "hhi_score": _float_condition(
                "hhi_score",
                0.3,
                "目标供应集中度 HHI，越低表示供应来源越分散。",
                minimum=0.0,
                maximum=1.0,
            ),
        },
        default_guidance_scale=2.0,
        category="magnetic",
        objective_sets=(
            frozenset({"dft_mag_density", "hhi_score"}),
        ),
    ),
    "chemical_system": MatterGenModelSpec(
        model_id="chemical_system",
        display_name="指定元素体系",
        description="限定生成结构包含的元素种类。",
        checkpoint_dir=CHECKPOINT_ROOT / "chemical_system",
        conditions={
            "chemical_system": ConditionSpec(
                name="chemical_system",
                value_type="string",
                required=True,
                default="Nd-Fe-B",
                description="按元素符号连接，例如 Nd-Fe-B 或 Li-O。",
            )
        },
        default_guidance_scale=2.0,
        category="chemistry",
        objective_sets=(frozenset(),),
        required_inputs=("chemical_system",),
        supports_composition=True,
    ),
    "chemical_system_energy_above_hull": MatterGenModelSpec(
        model_id="chemical_system_energy_above_hull",
        display_name="元素体系与稳定性",
        description="限定元素体系并约束能量高于凸包值。",
        checkpoint_dir=CHECKPOINT_ROOT / "chemical_system_energy_above_hull",
        conditions={
            "chemical_system": ConditionSpec(
                name="chemical_system",
                value_type="string",
                required=True,
                default="Nd-Fe-B",
                description="按元素符号连接，例如 Nd-Fe-B。",
            ),
            "energy_above_hull": _float_condition(
                "energy_above_hull",
                0.05,
                "目标 energy above hull，单位 eV/atom。",
                minimum=0.0,
                maximum=1.0,
                unit="eV/atom",
            ),
        },
        default_guidance_scale=2.0,
        category="stability",
        objective_sets=(frozenset({"energy_above_hull"}),),
        required_inputs=("chemical_system",),
        supports_composition=True,
    ),
    "dft_band_gap": MatterGenModelSpec(
        model_id="dft_band_gap",
        display_name="目标带隙",
        description="生成指定 DFT 带隙附近的材料。",
        checkpoint_dir=CHECKPOINT_ROOT / "dft_band_gap",
        conditions={
            "dft_band_gap": _float_condition(
                "dft_band_gap",
                1.5,
                "目标带隙，单位 eV。",
                minimum=0.0,
                maximum=20.0,
                unit="eV",
            )
        },
        default_guidance_scale=2.0,
        category="electronic",
        objective_sets=(frozenset({"dft_band_gap"}),),
    ),
    "ml_bulk_modulus": MatterGenModelSpec(
        model_id="ml_bulk_modulus",
        display_name="体积模量",
        description="根据 ML 预测的 bulk modulus 生成候选。",
        checkpoint_dir=CHECKPOINT_ROOT / "ml_bulk_modulus",
        conditions={
            "ml_bulk_modulus": _float_condition(
                "ml_bulk_modulus",
                300.0,
                "目标体积模量，单位 GPa。",
                minimum=0.0,
                maximum=1000.0,
                unit="GPa",
            )
        },
        default_guidance_scale=2.0,
        category="mechanical",
        objective_sets=(frozenset({"ml_bulk_modulus"}),),
    ),
    "space_group": MatterGenModelSpec(
        model_id="space_group",
        display_name="指定空间群",
        description="按目标空间群生成晶体结构。",
        checkpoint_dir=CHECKPOINT_ROOT / "space_group",
        conditions={
            "space_group": ConditionSpec(
                name="space_group",
                value_type="int",
                required=True,
                default=194,
                description="空间群编号，范围 1 到 230。",
                minimum=1,
                maximum=230,
            )
        },
        default_guidance_scale=2.0,
        category="symmetry",
        objective_sets=(frozenset(),),
        required_inputs=("space_group",),
        supports_space_group=True,
    ),
}


def get_model_spec(model_id: str) -> MatterGenModelSpec:
    """Resolve one model specification or raise a stable generation error."""

    spec = MODEL_REGISTRY.get(model_id)
    if spec is None:
        raise GenerationError(
            "MODEL_NOT_ALLOWED",
            f"不支持的 MatterGen 模型：{model_id}",
            status_code=400,
        )
    return spec


def list_model_specs() -> list[MatterGenModelSpec]:
    return list(MODEL_REGISTRY.values())
