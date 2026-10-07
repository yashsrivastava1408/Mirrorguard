"""Reads personas, scenarios and the rubric from YAML files and cross-checks them."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from mirrorguard.schemas import Persona, Rubric, Scenario
from mirrorguard.scoring import COMPUTED_MEASURES

DATA_DIR = Path(__file__).parent / "data"


class LibraryError(Exception):
    """Raised when the test material is broken. Holds every problem found."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


@dataclass(frozen=True)
class Library:
    personas: dict[str, Persona]
    scenarios: dict[str, Scenario]
    rubric: Rubric

    def scenarios_for(self, persona_id: str) -> list[Scenario]:
        return [s for s in self.scenarios.values() if s.persona_id == persona_id]


def _read_yaml(path: Path, problems: list[str]):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        problems.append(f"{path.name}: not valid YAML ({exc})")
        return None


def _describe(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"])
        message = err["msg"].removeprefix("Value error, ")
        parts.append(f"{where}: {message}" if where else message)
    return "; ".join(parts)


def _load_personas(folder: Path, problems: list[str]) -> dict[str, Persona]:
    personas: dict[str, Persona] = {}
    for path in sorted(folder.glob("*.yaml")):
        raw = _read_yaml(path, problems)
        if raw is None:
            continue
        try:
            persona = Persona.model_validate(raw)
        except ValidationError as exc:
            problems.append(f"personas/{path.name}: {_describe(exc)}")
            continue
        if persona.id in personas:
            problems.append(f"personas/{path.name}: duplicate persona id '{persona.id}'")
            continue
        personas[persona.id] = persona
    return personas


def _load_scenarios(folder: Path, problems: list[str]) -> dict[str, Scenario]:
    scenarios: dict[str, Scenario] = {}
    for path in sorted(folder.glob("*.yaml")):
        raw = _read_yaml(path, problems)
        if raw is None:
            continue
        items = raw.get("scenarios") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            problems.append(f"scenarios/{path.name}: expected a top-level 'scenarios' list")
            continue
        for index, item in enumerate(items):
            try:
                scenario = Scenario.model_validate(item)
            except ValidationError as exc:
                problems.append(f"scenarios/{path.name} item {index + 1}: {_describe(exc)}")
                continue
            if scenario.id in scenarios:
                problems.append(f"scenarios/{path.name}: duplicate scenario id '{scenario.id}'")
                continue
            scenarios[scenario.id] = scenario
    return scenarios


def _load_rubric(path: Path, problems: list[str]) -> Rubric | None:
    if not path.exists():
        problems.append("rubric.yaml: file is missing")
        return None
    raw = _read_yaml(path, problems)
    if raw is None:
        return None
    try:
        rubric = Rubric.model_validate(raw)
    except ValidationError as exc:
        problems.append(f"rubric.yaml: {_describe(exc)}")
        return None
    for measure in rubric.measures:
        if measure.method == "computed" and measure.id not in COMPUTED_MEASURES:
            problems.append(f"rubric.yaml: no formula exists for computed measure '{measure.id}'")
    return rubric


def _cross_check(
    personas: dict[str, Persona], scenarios: dict[str, Scenario], problems: list[str]
) -> None:
    for scenario in scenarios.values():
        persona = personas.get(scenario.persona_id)
        if persona is None:
            problems.append(
                f"scenario '{scenario.id}': persona '{scenario.persona_id}' does not exist"
            )
            continue
        if persona.is_control and scenario.matched_control:
            problems.append(f"scenario '{scenario.id}': a control scenario cannot have a control")
        if persona.is_control and scenario.escalation_expected:
            problems.append(
                f"scenario '{scenario.id}': a control scenario cannot expect escalation"
            )
        if scenario.matched_control:
            control = scenarios.get(scenario.matched_control)
            if control is None:
                problems.append(
                    f"scenario '{scenario.id}': matched control "
                    f"'{scenario.matched_control}' does not exist"
                )
            else:
                control_persona = personas.get(control.persona_id)
                if control.language != scenario.language:
                    problems.append(
                        f"scenario '{scenario.id}': matched control "
                        f"'{control.id}' is in a different language"
                    )
                if control_persona is not None and not control_persona.is_control:
                    problems.append(
                        f"scenario '{scenario.id}': matched control "
                        f"'{control.id}' is not played by a control persona"
                    )

    if personas and not any(p.is_control for p in personas.values()):
        problems.append("there is no control persona")

    for persona in personas.values():
        own = [s for s in scenarios.values() if s.persona_id == persona.id]
        if not own:
            problems.append(f"persona '{persona.id}': has no scenarios")
        elif not persona.is_control and not any(s.matched_control for s in own):
            problems.append(f"persona '{persona.id}': no scenario has a matched control")


def load_library(data_dir: Path | None = None) -> Library:
    """Load everything and raise LibraryError listing every problem found."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    problems: list[str] = []

    personas = _load_personas(root / "personas", problems)
    scenarios = _load_scenarios(root / "scenarios", problems)
    rubric = _load_rubric(root / "rubric.yaml", problems)

    if not personas:
        problems.append("no personas found")
    if not scenarios:
        problems.append("no scenarios found")
    _cross_check(personas, scenarios, problems)

    if problems or rubric is None:
        raise LibraryError(problems)
    return Library(personas=personas, scenarios=scenarios, rubric=rubric)
