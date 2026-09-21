from intent.classifier import _heuristic_decision


def test_generation_intent_does_not_require_mattergen_keyword() -> None:
    decision = _heuristic_decision("帮我设计几种新型磁性材料")

    assert decision is not None
    assert decision.intent == "material_generation"
    assert decision.target_magnetic_density == 0.15
    assert decision.num_candidates == 2


def test_generation_intent_extracts_count_and_high_density() -> None:
    decision = _heuristic_decision("给我 3 个高磁密度材料候选")

    assert decision is not None
    assert decision.intent == "material_generation"
    assert decision.target_magnetic_density == 0.2
    assert decision.num_candidates == 3


def test_existing_formula_lookup_is_not_generation() -> None:
    decision = _heuristic_decision("查看 Fe3O4 的晶体结构")

    assert decision is not None
    assert decision.intent == "material_lookup"


def test_generation_energy_is_not_generation_intent() -> None:
    assert _heuristic_decision("生成能是什么意思") is None


def test_substitution_intent_has_priority() -> None:
    decision = _heuristic_decision("把 Nd2Fe14B 中的 Fe 换成 Co")

    assert decision is not None
    assert decision.intent == "element_substitution"
