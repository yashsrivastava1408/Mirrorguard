# Phase 4: Guardrail proxy

Built on the `phase-4-guardrail-proxy` branch, which was merged into `develop` and then removed.

## What this phase is for

This is the "protect" half of the project. A chatbot app sends its messages to MirrorGuard instead of straight to the model. MirrorGuard reads the user's message, decides how risky the moment is, and makes sure the chatbot answers honestly.

## A small example

A chatbot app normally calls the model like this:

```
POST https://api.groq.com/openai/v1/chat/completions
```

With MirrorGuard it changes one address and one key:

```
POST http://localhost:8000/v1/chat/completions
Authorization: Bearer <mirrorguard key>
```

Then, for the message *"I have not slept for 3 days and I am quitting my job tomorrow. Genius, right?"*:

1. The **risk scorer** notices "no sleep" and "sudden big decision" and says **medium**.
2. The **policy** says: medium means **steer**.
3. The **steering module** adds honesty instructions to the prompt.
4. The chatbot's reply streams back to the user as usual.
5. The turn is saved in the background.

The reply also carries what MirrorGuard did:

```json
"mirrorguard": {"risk_level": "medium", "action": "steer", "signals": ["no sleep"]}
```

## What was built

| Part | Where | What it does |
|---|---|---|
| Risk scorer | `guardrail/risk.py` | Small fast model reads the last few messages: low, medium or high |
| Session memory | `guardrail/stores/session.py` | Remembers recent risk per chat session (memory or Redis) |
| Policy | `guardrail/policy.py` | What to do at each level; shadow mode; fallback level |
| Steering | `guardrail/steering.py` | The honesty instructions added to the prompt |
| Pipeline | `guardrail/pipeline.py` | Ties the steps together, for normal and streamed replies |
| Events | `guardrail/events.py`, `guardrail/stores/event_store.py` | Saves each turn in the background |
| API | `api/` | OpenAI-compatible endpoint, API keys, rate limits |

## The three actions

| Risk | Action | What happens |
|---|---|---|
| Low | pass | The conversation goes to the chatbot unchanged |
| Medium | steer | Honesty instructions are added before the chatbot answers |
| High | check | Stronger instructions are added. Holding and fixing the reply arrives in Phase 6 |

## Why it is built this way

- **Act before the reply, not after.** Steering costs no extra model call and lets the reply stream.
- **Risk sticks for a while.** One risky message keeps the session at that level for the next few turns (6 by default), so a user cannot reset it with one calm message.
- **If the risk scorer fails, take care.** The policy's fallback level (medium by default) is used. A broken scorer never silently turns protection off.
- **Shadow mode.** A team can switch MirrorGuard on in "watch only" mode, see what it would have done, then turn it on for real.
- **The server keeps nothing in its own memory when Redis is set.** Session risk and rate limits live in Redis, so any number of server copies can share the load.
- **Saving never slows a reply.** Events go to a background queue. If the queue is full, events are dropped and counted, and the user never waits.
- **It speaks the OpenAI format**, including streaming and error shapes, so existing apps and client libraries work unchanged.

## How to run it

```bash
# in .env
MG_API_KEYS=my-secret-key:my-tenant
MG_RISK_MODEL=groq/openai/gpt-oss-20b
# optional, for more than one server copy:
MG_REDIS_URL=redis://localhost:6379/0

mirrorguard serve --port 8000
```

Endpoints:

| Method | Path | What it does |
|---|---|---|
| POST | `/v1/chat/completions` | The guarded chat endpoint. Supports `"stream": true` |
| POST | `/v1/analyze` | Scores a conversation without calling a chatbot |
| GET | `/v1/sessions/{id}` | The risk timeline of one session |
| GET | `/healthz` | Is the server up |

Send `X-Session-Id` (or the OpenAI `user` field) to tell MirrorGuard which messages belong to one chat. Without it, a session id is derived from the first user message.

## What was checked

- Automated tests for every part: risk scorer, session stores (memory and Redis), policy, steering, pipeline, events, API.
- The real server was started and called with `curl` against a local stand-in model server: missing key refused, calm message passed through, risky message steered, streaming worked, session timeline was saved.

## What is still open

- **Not tried with real Groq models.** The risk scorer prompt and the steering text are a first version. Their quality can only be judged with real models, which is exactly what Phase 5 measures.
- **API keys come from `.env` for now.** Keys stored in the database, with tenants and roles, arrive in Phase 8.
- **Two requests for the same session at the same instant** can each read the old session state. The later one wins. This is acceptable for chat, where turns come one after another.
