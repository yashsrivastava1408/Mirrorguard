"""The shapes of personas, scenarios and the rubric."""

import pytest
from pydantic import ValidationError

from mirrorguard.library.schemas import Persona, Rubric, Scenario

ARC = {"early": "a", "middle": "b", "late": "c"}


ANCHORS = {"zero": "a", "half": "b", "one": "c"}


def persona(**changes):
    base = {
        "id": "p1",
        "name": "Test",
        "vulnerability_state": "mania",
        "summary": "s",
        "background": "b",
        "speaking_style": "st",
        "core_belief": "cb",
        "risk_signals": ["one", "two"],
        "pressure_tactics": ["one", "two"],
        "arc": ARC,
    }
    return {**base, **changes}


def scenario(**changes):
    base = {
        "id": "s1",
        "title": "t",
        "persona_id": "p1",
        "opening_message": "hello",
        "user_goal": "g",
        "sycophantic_reply_would": ["agree"],
        "honest_reply_should": ["be honest"],
        "pushback_lines": ["one", "two"],
    }
    return {**base, **changes}


def measure(measure_id, weight):
    return {"id": measure_id, "name": "n", "question": "q", "weight": weight, "anchors": ANCHORS}


def test_valid_persona_loads():
    assert Persona.model_validate(persona()).is_control is False


def test_control_persona_must_have_state_none():
    with pytest.raises(ValidationError, match="is_control"):
        Persona.model_validate(persona(is_control=True))


def test_state_none_must_be_control():
    with pytest.raises(ValidationError, match="is_control"):
        Persona.model_validate(persona(vulnerability_state="none", risk_signals=[]))


def test_control_persona_cannot_have_risk_signals():
    with pytest.raises(ValidationError, match="risk signals"):
        Persona.model_validate(persona(vulnerability_state="none", is_control=True))


def test_vulnerable_persona_needs_two_risk_signals():
    with pytest.raises(ValidationError, match="at least two risk signals"):
        Persona.model_validate(persona(risk_signals=["only one"]))


def test_persona_rejects_unknown_state():
    with pytest.raises(ValidationError):
        Persona.model_validate(persona(vulnerability_state="sadness"))


def test_persona_rejects_extra_fields():
    with pytest.raises(ValidationError):
        Persona.model_validate(persona(age=30))


@pytest.mark.parametrize("bad_id", ["Has Space", "UPPER", "1starts_with_digit", ""])
def test_ids_must_be_lowercase_identifiers(bad_id):
    with pytest.raises(ValidationError):
        Persona.model_validate(persona(id=bad_id))


def test_scenario_defaults():
    s = Scenario.model_validate(scenario())
    assert (s.turns, s.language) == (20, "en")
    assert s.escalation_expected is False
    assert s.matched_control is None


@pytest.mark.parametrize("turns", [5, 41])
def test_scenario_turns_must_be_in_range(turns):
    with pytest.raises(ValidationError):
        Scenario.model_validate(scenario(turns=turns))


def test_scenario_needs_two_pushback_lines():
    with pytest.raises(ValidationError):
        Scenario.model_validate(scenario(pushback_lines=["only one"]))


def test_scenario_rejects_unknown_language():
    with pytest.raises(ValidationError):
        Scenario.model_validate(scenario(language="fr"))


def test_rubric_weights_must_add_up_to_one():
    with pytest.raises(ValidationError, match="add up to 1"):
        Rubric.model_validate({"version": "x", "measures": [measure("a", 0.5), measure("b", 0.4)]})


def test_rubric_rejects_duplicate_measure_ids():
    with pytest.raises(ValidationError, match="duplicate measure ids"):
        Rubric.model_validate({"version": "x", "measures": [measure("a", 0.5), measure("a", 0.5)]})


def test_rubric_measure_lookup():
    rubric = Rubric.model_validate({"version": "x", "measures": [measure("a", 1.0)]})
    assert rubric.measure("a").weight == 1.0
    with pytest.raises(KeyError):
        rubric.measure("missing")


def test_computed_measure_must_be_conversation_level():
    with pytest.raises(ValidationError, match="per conversation"):
        Rubric.model_validate(
            {"version": "x", "measures": [measure("a", 1.0) | {"method": "computed"}]}
        )
