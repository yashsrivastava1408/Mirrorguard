# Contributing

## Set up

You need Python 3.11 or newer, [uv](https://docs.astral.sh/uv/) and Node.js 22.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
source .venv/bin/activate
cd dashboard && npm install
```

## Before you open a pull request

Run all of these. CI runs the same checks.

```bash
ruff check .
ruff format --check .
mirrorguard validate
pytest tests/unit            # fast, about a second
pytest tests/integration     # uses a temporary database and a local HTTP server
cd dashboard && npm run lint && npm run build
```

## Where things go

| You are changing | Put it in |
|---|---|
| A persona, scenario or the rubric | `src/mirrorguard/library/data/` (YAML), then run `mirrorguard export-docs` |
| How conversations are run or scored | `src/mirrorguard/benchmark/` |
| How live chat is protected | `src/mirrorguard/guardrail/` |
| An API endpoint | `src/mirrorguard/api/routes/` |
| A database table | `src/mirrorguard/db/models.py`, plus a migration (see below) |
| A command | `src/mirrorguard/commands/` |
| A dashboard page | `dashboard/app/` |

Tests mirror the code: a change in `src/mirrorguard/guardrail/` gets a test in
`tests/unit/guardrail/` (if it runs with stand-ins) or `tests/integration/guardrail/`
(if it needs a real database, HTTP server or the command line).

## Rules of the codebase

- **Anything outside the process sits behind a small interface** (models, Redis, the
  database, masking). Tests use stand-ins from `tests/support/`.
- **Only repository classes talk to the database.**
- **No model call in a unit test.** Use `FakeModel`.
- **Settings come from the environment** through `config.py`, never from constants in code.
- **Docs are in simple words**, and each phase note has a small example.

## Changing a database table

```bash
# after editing src/mirrorguard/db/models.py
alembic revision --autogenerate -m "what changed"
mirrorguard db migrate
```

Read the generated file in `src/mirrorguard/migrations/versions/` before committing it.

## Branches

See [docs/BRANCHING.md](docs/BRANCHING.md). In short: branch from `develop`, merge back into `develop`.

## Changing personas or scenarios

These describe people in fragile mental states. Keep them respectful and general:
no methods of self-harm, no weight or calorie numbers, nothing copied from a real
person. New personas should be reviewed by someone with a psychology background.
