"""Shared deterministic material vocabulary normalization."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Optional, Sequence


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

HEAVY_RARE_EARTH_ELEMENTS = [
    "Gd",
    "Tb",
    "Dy",
    "Ho",
    "Er",
    "Tm",
    "Yb",
    "Lu",
    "Y",
]

ELEMENT_GROUPS: dict[str, tuple[str, ...]] = {
    "rare_earth": tuple(RARE_EARTH_ELEMENTS),
    "heavy_rare_earth": tuple(HEAVY_RARE_EARTH_ELEMENTS),
}

ELEMENT_GROUP_ALIASES: dict[str, str] = {
    "rare_earth": "rare_earth",
    "rare-earth": "rare_earth",
    "rare earth": "rare_earth",
    "lanthanide": "rare_earth",
    "lanthanides": "rare_earth",
    "稀土": "rare_earth",
    "重稀土": "heavy_rare_earth",
    "heavy rare earth": "heavy_rare_earth",
}


@dataclass(frozen=True)
class NormalizedCompositionConstraints:
    """Expanded composition constraints used by planning and execution."""

    required_elements: tuple[str, ...]
    allowed_elements: tuple[str, ...]
    excluded_elements: tuple[str, ...]
    groups: dict[str, tuple[str, ...]]

    def as_dict(self) -> dict[str, object]:
        return {
            "required_elements": list(self.required_elements),
            "allowed_elements": list(self.allowed_elements),
            "excluded_elements": list(self.excluded_elements),
            "groups": {
                name: list(elements)
                for name, elements in self.groups.items()
            },
        }


class ConstraintConflict(ValueError):
    """Raised when composition constraints contradict each other."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def canonical_element_group(value: str) -> Optional[str]:
    return ELEMENT_GROUP_ALIASES.get(value.strip().lower())


def expand_element_group(value: str) -> list[str]:
    canonical = canonical_element_group(value)
    if canonical is None:
        return []
    return list(ELEMENT_GROUPS[canonical])


def normalize_composition_constraints(
    *,
    required_elements: Optional[Sequence[str]] = None,
    allowed_elements: Optional[Sequence[str]] = None,
    excluded_elements: Optional[Sequence[str]] = None,
    chemical_system: Optional[str] = None,
) -> NormalizedCompositionConstraints:
    """Expand groups and reject contradictory hard constraints."""

    required: list[str] = []
    allowed: list[str] = []
    excluded: list[str] = []
    groups: dict[str, tuple[str, ...]] = {}

    _append_elements(required, required_elements or [])
    _append_elements(allowed, allowed_elements or [])
    _append_elements(
        excluded,
        excluded_elements or [],
        groups=groups,
    )

    if chemical_system:
        _append_elements(
            allowed,
            [
                element
                for element in chemical_system.split("-")
                if element
            ],
        )

    required_set = set(required)
    allowed_set = set(allowed)
    excluded_set = set(excluded)

    conflicts = sorted(required_set.intersection(excluded_set))
    if conflicts:
        raise ConstraintConflict(
            "REQUIRED_ELEMENT_EXCLUDED",
            f"必需元素与排除约束冲突：{conflicts}",
        )

    conflicts = sorted(allowed_set.intersection(excluded_set))
    if conflicts:
        raise ConstraintConflict(
            "ALLOWED_ELEMENT_EXCLUDED",
            f"允许元素与排除约束冲突：{conflicts}",
        )

    if allowed_set and required_set - allowed_set:
        raise ConstraintConflict(
            "REQUIRED_ELEMENT_NOT_ALLOWED",
            f"必需元素不在允许集合中：{sorted(required_set - allowed_set)}",
        )

    return NormalizedCompositionConstraints(
        required_elements=tuple(required),
        allowed_elements=tuple(allowed),
        excluded_elements=tuple(excluded),
        groups=groups,
    )


def composition_violation(
    elements: Iterable[str],
    *,
    required_elements: Sequence[str],
    allowed_elements: Sequence[str],
    excluded_elements: Sequence[str],
) -> Optional[str]:
    """Return the first composition violation, if any."""

    normalized = normalize_composition_constraints(
        required_elements=required_elements,
        allowed_elements=allowed_elements,
        excluded_elements=excluded_elements,
    )
    present = set(elements)
    required = set(normalized.required_elements)
    allowed = set(normalized.allowed_elements)
    excluded = set(normalized.excluded_elements)

    missing = required - present
    if missing:
        return f"缺少必需元素：{sorted(missing)}"

    forbidden = present.intersection(excluded)
    if forbidden:
        return f"包含禁止元素：{sorted(forbidden)}"

    outside_allowed = present - allowed
    if allowed and outside_allowed:
        return f"包含允许范围外元素：{sorted(outside_allowed)}"
    return None


def _append_elements(
    target: list[str],
    values: Iterable[str],
    *,
    groups: Optional[dict[str, tuple[str, ...]]] = None,
) -> None:
    for value in values:
        canonical = canonical_element_group(value)
        if canonical is None:
            _append_unique(target, value)
            continue
        expanded = ELEMENT_GROUPS[canonical]
        if groups is not None:
            groups[canonical] = expanded
        for element in expanded:
            _append_unique(target, element)


def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)

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
