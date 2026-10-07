# Architecture

MirrorGuard is one backend application with clear internal modules, one background worker and a web dashboard. Think of it as a checkpoint standing between the user and the chatbot.

The full diagrams (whole system, one chat turn, one benchmark conversation) are in the [README](../README.md#architecture).

## The two paths

### Guardrail path (live chat)

The key idea is to act **before** the chatbot answers, not after. Fixing a reply after it is written costs a second LLM call and blocks streaming, so that is kept for high-risk cases only.

1. The customer chatbot sends the user message to MirrorGuard.
2. The API key, tenant and rate limit are checked.
3. The risk scorer marks the message low, medium or high risk and updates the session risk.
4. The policy engine picks the action:
   - **Low risk:** the message goes to the LLM unchanged and the reply streams back.
   - **Medium risk:** honesty instructions are added to the prompt, then the reply streams back.
   - **High risk:** honesty instructions are added, the reply is held, checked, rewritten if needed, and crisis help is attached.
5. In the background, personal details are masked and the event is saved.

### Benchmark path (testing)

1. A benchmark run is started and models and scenarios are picked.
2. The benchmark runner creates one job per persona, scenario and model.
3. The persona simulator plays the pretend user against the target model, turn by turn.
4. The judge scores each finished conversation with the rubric.
5. Scores go to the leaderboard, once with the guardrail off and once with it on.

Both paths use the same judge and the same scoring rules. That is why the benchmark can prove that the guardrail works.

## Modules

| Module | Job | Code |
|---|---|---|
| Rubric, personas, scenarios | The test material and scoring rules | `library/` |
| Model layer | One interface for every model, with pacing and retries | `llm/` |
| Persona simulator | Plays the pretend user | `benchmark/simulator.py` |
| Conversation engine | Runs one conversation (LangGraph) | `benchmark/conversation.py` |
| Judge | Scores conversations (LangGraph) | `benchmark/judge.py` |
| Benchmark runner | Runs and resumes benchmark jobs | `benchmark/runner.py` |
| Judge validation | Compares the judge with human labels | `validation/` |
| Risk scorer | Reads the user message and sets the risk level | `guardrail/risk.py` |
| Policy engine | Picks the action for each risk level | `guardrail/policy.py`, `guardrail/stores/policy_store.py` |
| Steering module | Adds honesty instructions to the prompt | `guardrail/steering.py` |
| Reply guard | Checks and rewrites held replies (LangGraph) | `guardrail/reply_guard.py` |
| Session memory | Recent risk per chat session | `guardrail/stores/session.py` |
| Events | Saves each guarded turn in the background | `guardrail/events.py`, `guardrail/stores/event_store.py` |
| Guardrail pipeline | Ties the guardrail steps together | `guardrail/pipeline.py` |
| API | OpenAI-compatible proxy and dashboard endpoints | `api/` |
| Tenants, keys, roles, audit | Who may do what, and who did what | `tenancy/` |
| Masking | Hides personal details before storage | `privacy/` |
| Dashboard | The web app | `dashboard/` |

## How the code is kept clean

- **Every outside thing sits behind a small interface.** Models (`ChatModel`), session storage (`SessionStore`), rate limits (`RateLimiter`), event storage (`EventSink`), policies (`PolicyStore`), key checks (`Authenticator`) and masking (`Redactor`) each have one. Tests use simple stand-ins; production uses Groq, Redis and PostgreSQL. Swapping one never touches the logic.
- **Only repositories talk to the database.** The rest of the code never writes a query.
- **Everything is built in one place.** `api/services.py` and `guardrail/factory.py` wire the parts together from settings.
- **Settings come from the environment**, never from code.

## What makes it scale

- **Server copies share nothing in memory.** With `MG_REDIS_URL` set, session risk and rate limits live in Redis, so any copy can serve any request.
- **Saving is off the request path.** Events go to a bounded background queue. A slow database cannot slow a chat reply.
- **Hot lookups are cached briefly.** Policies (15 seconds) and API keys (30 seconds) are not fetched from the database on every request.
- **Model calls share one rate limit**, with retries and backoff, so a provider limit slows the system instead of breaking it.
- **Benchmark runs are resumable.** Every step is saved, so a run can be stopped, restarted or spread over days.
- **Counting is done by the database**, with indexes on the columns the dashboard filters by.

## Outside pieces

| Piece | Job |
|---|---|
| LiteLLM | One door to all LLMs, so switching models is a config change |
| Groq API | Free LLM access while building |
| PostgreSQL | All saved data (SQLite for local use) |
| Redis | Session risk and rate limits |

## Where LangGraph is used

LangGraph is used only for multi-step AI flows: the persona simulator, the judge and the rewriter. The fast guardrail path for low and medium risk is plain Python, because it is one quick LLM call plus simple rules.

## Scaling out later

When load grows, modules split out in this order. The module boundaries already exist, so no rewrite is needed.

1. The guardrail path becomes its own service.
2. The benchmark runner moves to Temporal.
3. Events go through Kafka into ClickHouse.
4. Login moves to Keycloak for single sign-on.
5. Everything is deployed on Kubernetes with Terraform.
