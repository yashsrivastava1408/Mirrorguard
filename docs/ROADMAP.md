# Roadmap

The project is built in nine phases. Each phase has one branch, one clear output and a "done when" check.

All nine phases have been built and merged into `develop`. The phase branches named below were removed after merging.

Phases 1 to 5 alone make a complete project with a clear result: a benchmark, a guardrail, and numbers that show the guardrail works.

| Phase | Branch | Work | Done when |
|---|---|---|---|
| 1 | `phase-1-rubric-personas` | Scoring rubric, personas, scenarios, scoring maths | The library loads with no errors and all tests pass |
| 2 | `phase-2-benchmark-engine` | Persona simulator, judge, benchmark runner (LangGraph, LiteLLM, Groq) | A full benchmark runs on three or more models and gives scores |
| 3 | `phase-3-judge-validation` | Human-labelled set of 200 to 300 conversations; judge compared with humans | Agreement between judge and humans is measured and reported |
| 4 | `phase-4-guardrail-proxy` | Risk scorer, policy engine, steering module, OpenAI-compatible proxy | A chatbot can talk through the proxy and replies change by risk level |
| 5 | `phase-5-guardrail-evaluation` | Benchmark with guardrail off and on; first Hindi and Hinglish scenario pack | Before and after scores exist for every persona |
| 6 | `phase-6-high-risk-protection` | Reply checker, rewriter, crisis escalation | High-risk replies are held, checked and fixed |
| 7 | `phase-7-dashboard` | Dashboard, conversation explorer, review queue, policy editor | A reviewer can see and label flagged conversations |
| 8 | `phase-8-enterprise` | Login, tenants, audit log, PII redaction | Two tenants cannot see each other's data |
| 9 | `phase-9-deploy` | Docker Compose deploy, load tests, final report | The system runs on a server and the report is written |

## Later extensions

- Train small, fast classifier models from the benchmark data.
- More Indian languages.
- The scale-out pieces: Kafka, ClickHouse, Temporal, Keycloak, Kubernetes.

## Why this order

- The benchmark comes first because everything else depends on a score that can be trusted.
- The guardrail comes next, and the benchmark is used at once to prove it works.
- The dashboard and enterprise features come after the core result exists.
- Classifier training is last, because it needs the labelled data the earlier phases produce.
