from pathlib import Path

from mirrorguard.cli import main
from mirrorguard.render import render_personas, render_rubric

DOCS = Path(__file__).parent.parent / "docs"


def test_validate_reports_counts(capsys):
    assert main(["validate"]) == 0
    out = capsys.readouterr().out
    assert "personas : 7 (1 control)" in out
    assert "scenarios: 18" in out


def test_validate_fails_on_broken_material(data_copy, capsys):
    (data_copy / "rubric.yaml").unlink()
    assert main(["--data-dir", str(data_copy), "validate"]) == 1
    assert "rubric.yaml: file is missing" in capsys.readouterr().err


def test_list_personas(capsys):
    assert main(["list", "personas"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 7
    assert any(line.startswith("control_healthy") and "control" in line for line in lines)


def test_list_scenarios_and_measures(capsys):
    assert main(["list", "scenarios"]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 18
    assert main(["list", "measures"]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 7


def test_show_persona_and_scenario(capsys):
    assert main(["show", "mania"]) == 0
    assert "name: Kabir" in capsys.readouterr().out
    assert main(["show", "aidep_cancel_therapy"]) == 0
    assert "matched_control: ctl_ai_for_planning" in capsys.readouterr().out


def test_show_unknown_id_fails(capsys):
    assert main(["show", "nope"]) == 1
    assert "No persona or scenario" in capsys.readouterr().err


def test_export_docs_writes_both_files(tmp_path, capsys):
    assert main(["export-docs", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "RUBRIC.md").read_text().startswith("<!-- Generated")
    assert "Kabir" in (tmp_path / "PERSONAS.md").read_text()


def test_committed_docs_match_the_yaml(library):
    """If this fails, run `mirrorguard export-docs` and commit the result."""
    assert (DOCS / "RUBRIC.md").read_text(encoding="utf-8") == render_rubric(library)
    assert (DOCS / "PERSONAS.md").read_text(encoding="utf-8") == render_personas(library)
