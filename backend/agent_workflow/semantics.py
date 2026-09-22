"""Deterministic Chinese material-domain semantic normalization."""

from __future__ import annotations

import re

from agent_workflow.schemas import MaterialRequestSpec, ObjectiveSpec


RARE_EARTH_ELEMENTS = [
    "Sc",
    "Y",
    "La",
    "Ce",
    "Pr",
    "Nd",
    "Pm",
    "Sm",
    "Eu",
    "Gd",
    "Tb",
    "Dy",
    "Ho",
    "Er",
    "Tm",
    "Yb",
    "Lu",
]

ELEMENT_ALIASES = {
    "钕": "Nd",
    "铁": "Fe",
    "硼": "B",
    "钴": "Co",
    "镍": "Ni",
    "镝": "Dy",
    "镨": "Pr",
    "钐": "Sm",
    "铈": "Ce",
    "锰": "Mn",
    "铝": "Al",
    "铜": "Cu",
    "锌": "Zn",
    "氧": "O",
    "氮": "N",
    "碳": "C",
    "硅": "Si",
    "锂": "Li",
    "钠": "Na",
}

SYMBOL_PATTERN = re.compile(r"\b[A-Z][a-z]?\b")
CHEMICAL_SYSTEM_PATTERN = re.compile(
    r"\b[A-Z][a-z]?(?:-[A-Z][a-z]?)+\b"
)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _extract_requested_elements(text: str) -> list[str]:
    elements: list[str] = []
    if "钕铁硼" in text:
        elements.extend(["Nd", "Fe", "B"])
    elif "钕铁合金" in text or "钕铁" in text:
        elements.extend(["Nd", "Fe"])

    chemical_system_match = CHEMICAL_SYSTEM_PATTERN.search(text)
    if chemical_system_match:
        elements.extend(chemical_system_match.group(0).split("-"))

    for chinese_name, symbol in ELEMENT_ALIASES.items():
        if (
            f"含{chinese_name}" in text
            or f"加入{chinese_name}" in text
            or f"使用{chinese_name}" in text
        ):
            elements.append(symbol)
    return _unique(elements)


def _extract_excluded_elements(text: str) -> list[str]:
    excluded: list[str] = []
    if any(
        phrase in text
        for phrase in ("无稀土", "不含稀土", "零稀土", "禁止稀土")
    ):
        excluded.extend(RARE_EARTH_ELEMENTS)

    for marker in ("不含", "排除", "禁止", "去掉", "无"):
        start = text.find(marker)
        if start < 0:
            continue
        fragment = text[start + len(marker): start + len(marker) + 60]
        excluded.extend(SYMBOL_PATTERN.findall(fragment))
        for chinese_name, symbol in ELEMENT_ALIASES.items():
            if chinese_name in fragment:
                excluded.append(symbol)
    return _unique(excluded)


def _extract_allowed_elements(
    text: str,
    required_elements: list[str],
) -> list[str]:
    allowed = list(required_elements)
    for marker in ("允许", "加入"):
        start = text.find(marker)
        if start < 0:
            continue
        fragment = text[start + len(marker): start + len(marker) + 80]
        allowed.extend(SYMBOL_PATTERN.findall(fragment))
        for chinese_name, symbol in ELEMENT_ALIASES.items():
            if chinese_name in fragment:
                allowed.append(symbol)
    return _unique(allowed)


def _extract_objectives(text: str) -> tuple[list[ObjectiveSpec], list[str]]:
    objectives: list[ObjectiveSpec] = []
    ambiguities: list[str] = []

    if "磁" in text:
        target = 0.2 if "高磁" in text else 0.15
        match = re.search(
            r"磁密度[^\d]{0,8}(\d+(?:\.\d+)?)",
            text,
        )
        if match:
            target = float(match.group(1))
        objectives.append(
            ObjectiveSpec(
                property="dft_mag_density",
                operator=">=",
                target=target,
                kind="soft",
            )
        )
        if "较优" in text or "性能" in text:
            ambiguities.append(
                "“磁性性能较优”尚未指定具体指标，当前按 DFT 磁密度代理。"
            )

    if "稳定" in text or "凸包" in text:
        objectives.append(
            ObjectiveSpec(
                property="energy_above_hull",
                operator="<=",
                target=0.05,
                kind="soft",
            )
        )

    band_gap_match = re.search(
        r"带隙[^\d]{0,8}(\d+(?:\.\d+)?)",
        text,
    )
    if band_gap_match:
        objectives.append(
            ObjectiveSpec(
                property="dft_band_gap",
                operator="~=",
                target=float(band_gap_match.group(1)),
                kind="soft",
            )
        )

    return objectives, ambiguities


def extract_semantics(text: str) -> MaterialRequestSpec:
    """Extract chemistry and property constraints from Chinese/English text."""

    required = _extract_requested_elements(text)
    excluded = _extract_excluded_elements(text)
    required = [element for element in required if element not in excluded]
    allowed = _extract_allowed_elements(text, required)
    allowed = [element for element in allowed if element not in excluded]
    objectives, ambiguities = _extract_objectives(text)

    chemical_system = "-".join(allowed) if allowed else None
    material_type = None
    if "合金" in text:
        material_type = "alloy"
    elif "永磁" in text or "磁体" in text:
        material_type = "permanent_magnet"

    return MaterialRequestSpec(
        material_type=material_type,
        required_elements=required,
        allowed_elements=allowed,
        excluded_elements=excluded,
        chemical_system=chemical_system,
        objectives=objectives,
        ambiguities=ambiguities,
    )
