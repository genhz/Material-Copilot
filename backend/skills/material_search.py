"""
材料搜索工具 - 基于 LangChain Tool 接口封装 Materials Project API
"""
import os
from typing import Type, Optional
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool
from mp_api.client import MPRester


class MaterialSearchInput(BaseModel):
    """材料搜索工具的输入模型"""
    formula: str = Field(..., description="要查询的化学式，例如 'Nd2Fe14B', 'Fe3O4', 'LiCoO2'")


class MaterialSearchResult(BaseModel):
    """材料搜索结果"""
    formula: str
    material_id: str
    band_gap: Optional[float] = None
    is_magnetic: Optional[bool] = None
    formation_energy: Optional[float] = None
    cif: str
    density: Optional[float] = None
    spacegroup_symbol: Optional[str] = None
    spacegroup_number: Optional[int] = None
    crystal_system: Optional[str] = None
    formula_unit: Optional[int] = None
    magnetic_ordering: Optional[str] = None
    elements: Optional[list[str]] = None
    pretty_formula: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return self.model_dump()


class MaterialSearchTool(BaseTool):
    """
    材料搜索工具 - 查询 Materials Project 数据库获取晶体结构数据

    当用户需要了解具体材料的晶体结构、带隙、磁性等物理性质时使用。
    """
    name: str = "material_search"
    description: str = (
        "查询材料的晶体结构数据。"
        "当用户要求查看某个化学式的晶体结构、询问材料性质、或需要 3D 可视化时使用。"
        "输入应该是化学式，例如 'Nd2Fe14B', 'Fe3O4', 'LiCoO2'。"
        "返回材料的晶体结构 CIF 文件、带隙、磁性、形成能、空间群等信息。"
    )
    args_schema: Type[BaseModel] = MaterialSearchInput

    def _run(self, formula: str) -> str:
        """
        同步执行材料搜索

        Args:
            formula: 化学式

        Returns:
            JSON 格式的材料数据
        """
        result = self._search_material(formula)
        import json
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

    async def _arun(self, formula: str) -> str:
        """异步执行材料搜索（使用同步实现）"""
        return self._run(formula)

    def _search_material(self, formula: str) -> MaterialSearchResult:
        """
        通过 mp-api 查询材料数据

        Args:
            formula: 化学式

        Returns:
            MaterialSearchResult: 材料数据

        Raises:
            ValueError: 未找到材料
            RuntimeError: API Key 未配置
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

        print(f"[MaterialSearchTool] 查询成功：{result.formula} ({result.material_id})")
        return result
