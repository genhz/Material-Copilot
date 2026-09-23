"""Shared deterministic material vocabulary normalization."""

from __future__ import annotations

import re


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

CHEMICAL_SYSTEM_PATTERN = re.compile(
    r"\b[A-Z][a-z]?(?:-[A-Z][a-z]?)+\b"
)


def extract_requested_elements(text: str) -> list[str]:
    """Extract explicitly named elements without choosing a model."""

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
    return list(dict.fromkeys(elements))
