"""
元素替换工具 - 基于 LangChain Tool 接口封装晶体结构元素替换功能

使用 pymatgen 修改晶体结构中的元素，生成新的 CIF 结构和化学式。
优先从 Materials Project 查询替换后材料的数据，找不到时使用计算值并标注。

使用示例:
    # 用户说："把 Nd2Fe14B 中的 Fe 替换成 Co"
    # Agent 会自动调用此工具：
    # element_substitution(
    #     cif="...CIF 内容...",
    #     substitutions={"Fe": "Co"},
    #     current_formula="Nd2Fe14B"
    # )
"""
import os
import json
import logging
from pathlib import Path
from typing import Type, Optional, Dict, List, Tuple
from pydantic import BaseModel, Field

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parents[1] / "artifacts" / "matplotlib"),
)

from langchain_core.tools import BaseTool
from pymatgen.core.structure import Structure
from pymatgen.core.periodic_table import Element
from mp_api.client import MPRester

logger = logging.getLogger(__name__)


class ElementSubstitutionInput(BaseModel):
    """元素替换工具的输入模型"""
    cif: str = Field(..., description="当前材料的 CIF 文件内容")
    substitutions: Dict[str, str] = Field(
        ...,
        description="元素替换规则，键为原元素，值为目标元素。例如：{'Fe': 'Co', 'Nd': 'La'}"
    )
    current_formula: str = Field(..., description="当前材料的化学式，用于生成回复")


class MaterialSearchResult(BaseModel):
    """材料搜索结果（与 material_search.py 保持一致）"""
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
    # 数据来源标记
    data_source: str = "MP"  # "MP" = Materials Project, "calculated" = 计算值
    note: Optional[str] = None  # 额外说明

    def to_dict(self) -> dict:
        """转换为字典"""
        return self.model_dump()


class ElementSubstitutionTool(BaseTool):
    """
    元素替换工具 - 修改晶体结构中的元素并生成新的结构

    当用户想要进行元素掺杂、替代或修改化学式时使用。
    例如："把 Fe 替换成 Co"、"用 La 替代 Nd"、"将 Nd2Fe14B 中的 Fe 全部替换为 Co"

    策略：
    1. 先执行元素替换，生成新结构的 CIF 和化学式
    2. 尝试用新化学式从 Materials Project 查询真实数据
    3. 如果 MP 有数据，使用 MP 的真实物性数据
    4. 如果 MP 没有，使用结构计算的几何数据（密度、空间群等），物性数据标记为"需 DFT 计算"
    """
    name: str = "element_substitution"
    description: str = (
        "替换晶体结构中的元素。"
        "当用户要求进行元素替代、掺杂、或修改化学式时使用。"
        "需要提供当前材料的 CIF 文件内容和替换规则。"
        "例如：'把 Fe 替换成 Co'、'用 La 替代 Nd'、'将 Nd2Fe14B 中的 Fe 全部替换为 Co'"
        "返回替换后的新结构 CIF、新化学式、以及晶体学信息。"
        "会优先从 Materials Project 查询替换后材料的真实数据，找不到时使用计算值并标注。"
    )
    args_schema: Type[BaseModel] = ElementSubstitutionInput

    def _run(
        self,
        cif: str,
        substitutions: Dict[str, str],
        current_formula: str,
    ) -> str:
        """
        同步执行元素替换

        Args:
            cif: 当前材料的 CIF 文件内容
            substitutions: 元素替换规则，如 {'Fe': 'Co', 'Nd': 'La'}
            current_formula: 当前化学式

        Returns:
            JSON 格式的替换后材料数据
        """
        result = self._substitute_elements(cif, substitutions, current_formula)
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

    async def _arun(
        self,
        cif: str,
        substitutions: Dict[str, str],
        current_formula: str,
    ) -> str:
        """异步执行元素替换（使用同步实现）"""
        return self._run(cif, substitutions, current_formula)

    def _substitute_elements(
        self,
        cif: str,
        substitutions: Dict[str, str],
        current_formula: str,
    ) -> MaterialSearchResult:
        """
        执行元素替换并返回新材料数据

        策略：
        1. 执行元素替换，生成新结构
        2. 用新化学式查询 Materials Project
        3. 如果 MP 有数据，使用 MP 的真实数据
        4. 如果 MP 没有，使用计算值并标注

        Args:
            cif: CIF 文件内容
            substitutions: 替换规则
            current_formula: 原化学式

        Returns:
            MaterialSearchResult: 替换后的材料数据
        """
        try:
            # 步骤 1: 从 CIF 解析晶体结构
            structure = Structure.from_str(cif, fmt="cif")

            # 步骤 2: 执行元素替换
            modified_structure = self._apply_substitutions(structure, substitutions)

            # 步骤 3: 生成新的 CIF 和化学式
            new_cif = modified_structure.to(fmt="cif")
            new_formula = self._generate_formula(modified_structure)

            logger.info(f"[ElementSubstitution] 替换成功：{current_formula} → {new_formula}")
            logger.info(f"[ElementSubstitution] 替换规则：{substitutions}")

            # 步骤 4: 尝试从 Materials Project 查询新化学式的真实数据
            mp_data = self._try_query_mp(new_formula)

            if mp_data:
                # MP 有数据，使用真实物性
                logger.info(f"[ElementSubstitution] MP 查询成功：{mp_data.material_id}")
                return MaterialSearchResult(
                    formula=new_formula,
                    material_id=mp_data.material_id,
                    band_gap=mp_data.band_gap,
                    is_magnetic=mp_data.is_magnetic,
                    formation_energy=mp_data.formation_energy,
                    cif=new_cif,  # 使用替换后的 CIF（保持晶体框架）
                    density=mp_data.density,
                    spacegroup_symbol=mp_data.spacegroup_symbol,
                    spacegroup_number=mp_data.spacegroup_number,
                    crystal_system=mp_data.crystal_system,
                    formula_unit=mp_data.formula_unit,
                    magnetic_ordering=mp_data.magnetic_ordering,
                    elements=mp_data.elements,
                    pretty_formula=mp_data.pretty_formula,
                    data_source="MP",
                    note=f"元素替换后从 MP 查询到 {mp_data.material_id} 的真实数据",
                )
            else:
                # MP 没有数据，使用计算值
                logger.info(f"[ElementSubstitution] MP 未找到 {new_formula}，使用计算值")
                spacegroup_info = self._get_spacegroup_info(modified_structure)

                return MaterialSearchResult(
                    formula=new_formula,
                    material_id="substituted",  # 标记为人工替换结构
                    band_gap=None,
                    is_magnetic=None,
                    formation_energy=None,
                    cif=new_cif,
                    density=modified_structure.density,
                    spacegroup_symbol=spacegroup_info["symbol"],
                    spacegroup_number=spacegroup_info["number"],
                    crystal_system=spacegroup_info["crystal_system"],
                    formula_unit=len(modified_structure),
                    magnetic_ordering=None,
                    elements=list(set(site.species.elements[0].symbol for site in modified_structure)),
                    pretty_formula=new_formula,
                    data_source="calculated",
                    note="替换后的材料在 Materials Project 中未找到，物性数据需 DFT 计算",
                )

        except Exception as e:
            logger.exception(f"[ElementSubstitution] 替换失败：{e}")
            raise ValueError(f"元素替换失败：{str(e)}")

    def _try_query_mp(self, formula: str) -> Optional[MaterialSearchResult]:
        """
        尝试从 Materials Project 查询指定化学式的材料数据

        Args:
            formula: 化学式

        Returns:
            MaterialSearchResult 如果找到，否则 None
        """
        mp_api_key = os.getenv("MP_API_KEY", "")
        if not mp_api_key:
            logger.warning("[ElementSubstitution] MP_API_KEY 未配置，跳过 MP 查询")
            return None

        try:
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
                return None

            # 取 formation_energy_per_atom 最低的最稳定结构
            best_doc = sorted(docs, key=lambda x: x.formation_energy_per_atom or 0)[0]

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

            return MaterialSearchResult(
                formula=formula,
                material_id=getattr(best_doc, "material_id", "unknown") or "unknown",
                band_gap=getattr(best_doc, "band_gap", None),
                is_magnetic=getattr(best_doc, "is_magnetic", None),
                formation_energy=getattr(best_doc, "formation_energy_per_atom", None),
                cif="",  # 占位，实际使用替换后的 CIF
                density=getattr(best_doc, "density", None),
                spacegroup_symbol=spacegroup_symbol,
                spacegroup_number=spacegroup_number,
                crystal_system=crystal_system,
                formula_unit=getattr(best_doc, "nsites", None),
                magnetic_ordering=magnetic_ordering,
                elements=elements_list,
                pretty_formula=getattr(best_doc, "formula_pretty", None),
                data_source="MP",
            )

        except Exception as e:
            logger.warning(f"[ElementSubstitution] MP 查询失败：{e}")
            return None

    def _apply_substitutions(
        self,
        structure: Structure,
        substitutions: Dict[str, str],
    ) -> Structure:
        """
        应用元素替换规则到晶体结构

        Args:
            structure: pymatgen Structure 对象
            substitutions: 替换规则 {'原元素': '目标元素'}

        Returns:
            修改后的 Structure 对象
        """
        # 创建结构的副本，避免修改原结构
        modified = structure.copy()

        for original_element, target_element in substitutions.items():
            try:
                # 验证元素符号有效性
                Element(original_element)
                Element(target_element)

                # 遍历所有原子位点
                for site in modified.sites:
                    # 获取位点上的主要元素
                    species = site.species.elements[0]
                    if species.symbol == original_element:
                        # 替换元素（保持占位率不变）
                        # 使用 site.species 的字典 API
                        occu = float(site.species[species])
                        site.species = {Element(target_element): occu}

                logger.info(f"[ElementSubstitution] 已替换 {original_element} → {target_element}")

            except ValueError as e:
                raise ValueError(f"无效的元素符号：{original_element} 或 {target_element}") from e

        return modified

    def _generate_formula(self, structure: Structure) -> str:
        """
        从结构生成化学式

        Args:
            structure: pymatgen Structure 对象

        Returns:
            化学式字符串
        """
        # 获取元素计数
        composition = structure.composition
        formula = composition.reduced_formula

        return formula

    def _get_spacegroup_info(self, structure: Structure) -> Dict[str, Optional[str | int]]:
        """
        获取空间群信息

        Args:
            structure: pymatgen Structure 对象

        Returns:
            包含空间群符号、编号、晶系的字典
        """
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

        try:
            analyzer = SpacegroupAnalyzer(structure)
            sg_data = analyzer.get_space_group_data()

            return {
                "symbol": sg_data.symbol,
                "number": sg_data.int_number,
                "crystal_system": sg_data.crystal_system,
            }
        except Exception as e:
            logger.warning(f"[ElementSubstitution] 无法获取空间群信息：{e}")
            return {
                "symbol": None,
                "number": None,
                "crystal_system": None,
            }
