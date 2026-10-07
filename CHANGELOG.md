# Changelog

All notable changes to this project are listed here.

## Unreleased

### Changed
- Test material moved into its own package, `mirrorguard.library`.
- Guardrail storage (sessions, events, policies) moved to `mirrorguard.guardrail.stores`.
- Command line code split into one file per command group.
- Tests split into `tests/unit` and `tests/integration`, in folders that mirror the code.
- README: architecture shown as diagrams, with a guide to each component and the full tech stack.

### Added
- `LICENSE` (MIT), `CONTRIBUTING.md`, `SECURITY.md` and this changelog.

### Removed
- The one-time script and snapshots that created the initial git history.

## 0.1.0 - 2026-10-07

First complete version. Tested with stand-in models only; no results from real models yet.

### Added
- **Phase 1.** Scoring rubric with seven measures, seven personas, scenarios with matched controls.
- **Phase 2.** Persona simulator, conversation engine, judge and a resumable benchmark runner.
- **Phase 3.** Blind labelling sheets and agreement statistics for checking the judge against people.
- **Phase 4.** Guardrail proxy with an OpenAI-compatible API: risk scorer, session memory, policy, steering.
- **Phase 5.** Benchmark with the guardrail off and on; Hinglish scenario pack; per-language report.
- **Phase 6.** Hold, check and rewrite for high-risk replies; crisis helpline message.
- **Phase 7.** Web dashboard and the endpoints behind it.
- **Phase 8.** Tenants, hashed API keys, roles, audit log, masking of personal details, retention.
- **Phase 9.** Database migrations, Docker files, CI workflow and a load test.
