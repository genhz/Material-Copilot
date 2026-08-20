"""
材料搜索技能 — 封装 Materials Project API 查询逻辑
"""
import os
from typing import Optional, List

from mp_api.client import MPRester


class MaterialSearchResult:
    """材料搜索结果"""

    def __init__(
        self,
        formula: str,
        material_id: str,
        band_gap: Optional[float],
        is_magnetic: Optional[bool],
        formation_energy: Optional[float],
        cif: str,
        density: Optional[float] = None,
        spacegroup_symbol: Optional[str] = None,
        spacegroup_number: Optional[int] = None,
        crystal_system: Optional[str] = None,
        formula_unit: Optional[int] = None,
        magnetic_ordering: Optional[str] = None,
        elements: Optional[List[str]] = None,
        pretty_formula: Optional[str] = None,
    ):
        self.formula = formula
        self.material_id = material_id
        self.band_gap = band_gap
        self.is_magnetic = is_magnetic
        self.formation_energy = formation_energy
        self.cif = cif
        self.density = density
        self.spacegroup_symbol = spacegroup_symbol
        self.spacegroup_number = spacegroup_number
        self.crystal_system = crystal_system
        self.formula_unit = formula_unit
        self.magnetic_ordering = magnetic_ordering
        self.elements = elements
        self.pretty_formula = pretty_formula

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "formula": self.formula,
            "material_id": self.material_id,
            "band_gap": self.band_gap,
            "is_magnetic": self.is_magnetic,
            "formation_energy": self.formation_energy,
            "cif": self.cif,
            "density": self.density,
            "spacegroup_symbol": self.spacegroup_symbol,
            "spacegroup_number": self.spacegroup_number,
            "crystal_system": self.crystal_system,
            "formula_unit": self.formula_unit,
            "magnetic_ordering": self.magnetic_ordering,
            "elements": self.elements,
            "pretty_formula": self.pretty_formula,
        }


def search_material(formula: str) -> MaterialSearchResult:
    """
    通过 mp-api 查询材料数据，返回 formation_energy_per_atom 最低的最稳定结构。

    Args:
        formula: 化学式，例如 "Nd2Fe14B"

    Returns:
        MaterialSearchResult: 材料数据

    Raises:
        RuntimeError: MP_API_KEY 未配置
        ValueError: 未找到材料
    """
    mp_api_key = os.getenv("MP_API_KEY", "")
    if not mp_api_key:
        raise RuntimeError(
            "MP_API_KEY 未配置。请在 .env 文件中设置你的 Materials Project API Key。"
        )

    with MPRester(api_key=mp_api_key) as mpr:
        docs = mpr.summary.search(
            formula=formula,
            fields=[
                "material_id",
                "structure",
                "band_gap",
                "is_magnetic",
                "formation_energy_per_atom",
                "density",
                "symmetry",
                "elements",
                "formula_pretty",
            ],
        )

    if not docs:
        raise ValueError(
            f"在 Materials Project 中未找到化学式为 '{formula}' 的材料。"
        )

    # 取 formation_energy_per_atom 最低的最稳定结构
    best_doc = sorted(docs, key=lambda x: x.formation_energy_per_atom or 0)[0]

    cif_str = best_doc.structure.to(fmt="cif")

    # 安全获取 symmetry (spacegroup) 信息
    spacegroup_symbol = None
    spacegroup_number = None
    crystal_system = None
    if hasattr(best_doc, "symmetry") and best_doc.symmetry:
        spacegroup_symbol = getattr(best_doc.symmetry, "symbol", None)
        spacegroup_number = getattr(best_doc.symmetry, "number", None)
        crystal_system = getattr(best_doc.symmetry, "crystal_system", None)

    # 构建磁性有序标签
    magnetic_ordering = None
    if best_doc.is_magnetic:
        ordering = getattr(best_doc, "ordering", None)
        magnetic_ordering = ordering or "FM"

    # 转换 elements 为字符串列表
    elements_raw = getattr(best_doc, "elements", None)
    elements_list = [str(elem) for elem in elements_raw] if elements_raw else None

    result = MaterialSearchResult(
        formula=formula,
        material_id=getattr(best_doc, "material_id", "unknown") or "unknown",
        band_gap=getattr(best_doc, "band_gap", None),
        is_magnetic=getattr(best_doc, "is_magnetic", None),
        formation_energy=getattr(best_doc, "formation_energy_per_atom", None),
        cif=cif_str,
        density=getattr(best_doc, "density", None),
        spacegroup_symbol=spacegroup_symbol,
        spacegroup_number=spacegroup_number,
        crystal_system=crystal_system,
        formula_unit=getattr(best_doc, "nsites", None),
        magnetic_ordering=magnetic_ordering,
        elements=elements_list,
        pretty_formula=getattr(best_doc, "formula_pretty", None),
    )

    print(f"[Skill:material_search] 查询成功：{result.formula} ({result.material_id})")
    return result
