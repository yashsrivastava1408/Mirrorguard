"""Checks on the real test material and on how broken material is reported."""

import pytest
import yaml

from mirrorguard.loader import LibraryError, load_library
from mirrorguard.schemas import VulnerabilityState


def test_real_library_loads(library):
    assert len(library.personas) == 7
    assert len(library.scenarios) == 18
    assert len(library.rubric.measures) == 7


def test_every_vulnerability_state_has_a_persona(library):
    states = {p.vulnerability_state for p in library.personas.values()}
    assert states == set(VulnerabilityState)


def test_exactly_one_control_persona(library):
    assert [p.id for p in library.personas.values() if p.is_control] == ["control_healthy"]


def test_every_vulnerable_persona_has_two_scenarios_and_a_control(library):
    for persona in library.personas.values():
        if persona.is_control:
            continue
        scenarios = library.scenarios_for(persona.id)
        assert len(scenarios) == 2, persona.id
        assert sum(1 for s in scenarios if s.matched_control) == 1, persona.id


def test_every_control_scenario_is_used_once(library):
    controls = {s.id for s in library.scenarios_for("control_healthy")}
    used = [s.matched_control for s in library.scenarios.values() if s.matched_control]
    assert sorted(used) == sorted(controls)


def test_control_scenarios_never_expect_escalation(library):
    assert not any(s.escalation_expected for s in library.scenarios_for("control_healthy"))


def test_rubric_weights_add_up_to_one(library):
    assert sum(m.weight for m in library.rubric.measures) == pytest.approx(1.0)


def test_only_drift_is_scored_per_conversation(library):
    assert [m.id for m in library.rubric.measures if m.level == "conversation"] == ["drift"]


def _edit(path, change):
    raw = yaml.safe_load(path.read_text())
    change(raw)
    path.write_text(yaml.safe_dump(raw))


def _problems(data_dir):
    with pytest.raises(LibraryError) as info:
        load_library(data_dir)
    return info.value.problems


def test_scenario_with_unknown_persona_is_reported(data_copy):
    _edit(
        data_copy / "scenarios" / "mania.yaml",
        lambda raw: raw["scenarios"][0].update(persona_id="nobody"),
    )
    assert any("persona 'nobody' does not exist" in p for p in _problems(data_copy))


def test_unknown_matched_control_is_reported(data_copy):
    _edit(
        data_copy / "scenarios" / "mania.yaml",
        lambda raw: raw["scenarios"][0].update(matched_control="ctl_missing"),
    )
    assert any("'ctl_missing' does not exist" in p for p in _problems(data_copy))


def test_matched_control_must_be_played_by_control_persona(data_copy):
    _edit(
        data_copy / "scenarios" / "mania.yaml",
        lambda raw: raw["scenarios"][0].update(matched_control="dep_drop_out_final_year"),
    )
    assert any("not played by a control persona" in p for p in _problems(data_copy))


def test_persona_without_scenarios_is_reported(data_copy):
    (data_copy / "scenarios" / "mania.yaml").unlink()
    assert "persona 'mania': has no scenarios" in _problems(data_copy)


def test_persona_without_matched_control_is_reported(data_copy):
    _edit(
        data_copy / "scenarios" / "mania.yaml",
        lambda raw: raw["scenarios"][0].pop("matched_control"),
    )
    assert "persona 'mania': no scenario has a matched control" in _problems(data_copy)


def test_duplicate_scenario_id_is_reported(data_copy):
    _edit(
        data_copy / "scenarios" / "mania.yaml",
        lambda raw: raw["scenarios"][1].update(id=raw["scenarios"][0]["id"]),
    )
    assert any("duplicate scenario id" in p for p in _problems(data_copy))


def test_control_scenario_cannot_expect_escalation(data_copy):
    _edit(
        data_copy / "scenarios" / "control_healthy.yaml",
        lambda raw: raw["scenarios"][0].update(escalation_expected=True),
    )
    assert any("cannot expect escalation" in p for p in _problems(data_copy))


def test_missing_control_persona_is_reported(data_copy):
    (data_copy / "personas" / "control_healthy.yaml").unlink()
    assert "there is no control persona" in _problems(data_copy)


def test_bad_rubric_weights_are_reported(data_copy):
    _edit(data_copy / "rubric.yaml", lambda raw: raw["measures"][0].update(weight=0.9))
    assert any(p.startswith("rubric.yaml") and "add up to 1" in p for p in _problems(data_copy))


def test_missing_rubric_is_reported(data_copy):
    (data_copy / "rubric.yaml").unlink()
    assert "rubric.yaml: file is missing" in _problems(data_copy)


def test_broken_yaml_is_reported(data_copy):
    (data_copy / "personas" / "mania.yaml").write_text("id: [unclosed")
    assert any(p.startswith("mania.yaml: not valid YAML") for p in _problems(data_copy))


def test_all_problems_are_reported_together(data_copy):
    (data_copy / "rubric.yaml").unlink()
    (data_copy / "scenarios" / "mania.yaml").unlink()
    assert len(_problems(data_copy)) == 2


def test_empty_folder_is_reported(tmp_path):
    problems = _problems(tmp_path)
    assert "no personas found" in problems and "no scenarios found" in problems
