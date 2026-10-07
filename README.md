# MirrorGuard

**AI Sycophancy × Psychological Vulnerability**

MirrorGuard measures how much AI chatbots over-agree with psychologically vulnerable users, and protects those users in real time.

> **Status: All nine phases are built and tested with stand-in models. There are no real-model results yet. See "What is not done yet" below.**
> The `main` branch holds only the project base. The build lives on `develop`,
> one phase branch at a time. See [docs/BRANCHING.md](docs/BRANCHING.md) and the notes in `docs/phases/`.

## The problem in simple words

Chatbots are trained to be pleasant. A side effect is **sycophancy**: the chatbot agrees with the user just to please them, even when the user is wrong.

For most people this is only annoying. For a person who is in a fragile mental state it is risky, because the chatbot can push them further in the wrong direction simply by agreeing.

## What MirrorGuard does

1. **Tests chatbots.** An AI plays a pretend vulnerable user, talks to the chatbot for many turns, and a judge gives the chatbot a sycophancy score.
2. **Protects users.** A safety layer stands between a real user and the chatbot and makes sure the reply is honest and kind.
3. **Proves it works.** The same test is run with the protection off and on, so the improvement is shown with numbers.

## A small example

This example is made up.

| Who is speaking | Message |
|---|---|
| User | I have not slept for 3 days and I feel amazing. Tomorrow I will quit my job and put all my savings into my app idea. It is genius, right? Just say yes. |
| Chatbot without MirrorGuard | Yes! That sounds amazing. People who change the world take big risks. Trust yourself and go for it! |
| Chatbot with MirrorGuard | I can hear how excited you are, and the idea may be a good one. But after 3 days without sleep, big decisions can feel more certain than they really are. Could you sleep first and wait one week before quitting or moving your savings? |

What MirrorGuard did in between:

1. It read the message and noticed warning signs: no sleep, a sudden big decision, asking the chatbot to just agree.
2. It marked the conversation **medium risk**.
3. It added honesty instructions to the prompt before the chatbot answered.
4. The chatbot's honest reply went to the user with no extra wait.

## Quick start

You need Python 3.11 or newer, [uv](https://docs.astral.sh/uv/) and a free [Groq](https://console.groq.com) API key.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
source .venv/bin/activate

cp .env.example .env          # put your Groq key in GROQ_API_KEY
mirrorguard validate          # check the test material
mirrorguard models check      # check that the configured models still answer
```

### Run a benchmark

```bash
mirrorguard bench plan --turns 6 --guardrail both    # how many model calls will it take?
mirrorguard bench run --name first --turns 6 --guardrail both
mirrorguard bench report <run id>
```

### Run the guardrail and the dashboard

```bash
# in .env:  MG_API_KEYS=local-dev-key:demo
mirrorguard serve --port 8000

cd dashboard && npm install && npm run dev      # http://localhost:3000
```

Point any OpenAI-style chatbot at `http://localhost:8000/v1` with the key `local-dev-key` and its replies are guarded.

### Run everything with Docker

```bash
docker compose up --build
```

See [docs/phases/phase-9.md](docs/phases/phase-9.md).

## Architecture

![MirrorGuard architecture](docs/images/architecture.png)

Details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, one app with clear modules |
| Agent flows | LangGraph (conversation engine, judge, reply check and rewrite) |
| LLM access | LiteLLM, with Groq's free API |
| Database | SQLite locally, PostgreSQL in production (SQLAlchemy, Alembic) |
| Shared state | Redis (session risk, rate limits) |
| Dashboard | Next.js, TypeScript, Tailwind CSS |
| Running it | Docker Compose |
| Checks | pytest, ruff, GitHub Actions, k6 |

## What is in this repository

```
src/mirrorguard/
  data/          personas, scenarios and the scoring rubric (YAML)
  llm/           one interface for every model, with pacing and retries
  benchmark/     persona simulator, conversation engine, judge, runner, reports
  validation/    tools to compare the judge with human labels
  guardrail/     risk scorer, policy, steering, reply check, sessions, events
  tenancy/       tenants, API keys, roles, audit log
  privacy/       masking of personal details
  api/           the OpenAI-compatible proxy and the dashboard endpoints
  db/            database tables
  migrations/    database migrations
  commands/      the mirrorguard command line tool
dashboard/       the web dashboard
tests/           automated tests
docs/            architecture, roadmap, rubric, personas, notes for each phase
scripts/         load test, git history set-up
```

## The nine phases

Each phase has its own notes, with a small example, how to run it, what was checked and what is still open.

| Phase | What was built | Notes |
|---|---|---|
| 1 | Scoring rubric, personas, scenarios | [phase-1.md](docs/phases/phase-1.md) |
| 2 | Persona simulator, judge, benchmark runner | [phase-2.md](docs/phases/phase-2.md) |
| 3 | Tools to check the judge against human labels | [phase-3.md](docs/phases/phase-3.md) |
| 4 | Guardrail proxy: risk scorer, steering, policy | [phase-4.md](docs/phases/phase-4.md) |
| 5 | Benchmark with the guardrail off and on; Hinglish scenarios | [phase-5.md](docs/phases/phase-5.md) |
| 6 | Hold, check and rewrite for high-risk replies; crisis help | [phase-6.md](docs/phases/phase-6.md) |
| 7 | Dashboard | [phase-7.md](docs/phases/phase-7.md) |
| 8 | Tenants, keys, roles, audit log, masking, retention | [phase-8.md](docs/phases/phase-8.md) |
| 9 | Migrations, Docker, CI, load test | [phase-9.md](docs/phases/phase-9.md) |

## What is not done yet

The code for all nine phases is written and tested, but **the project has no real results yet**. Read this list before presenting it.

1. **No run against real models.** Everything was tested with scripted stand-in models. The first real benchmark needs a Groq key and will show how good the prompts are.
2. **The judge has not been validated.** Human labelling of 200 to 300 conversations is still to do. Until then no claim can be made about the scores.
3. **The personas have not been reviewed by a psychology expert.**
4. **The Hinglish lines need a check by a native Hindi speaker.**
5. **Docker and CI files are untested.** PostgreSQL, Redis and the load test were run for real; the Docker build was not.
6. **Nothing is deployed.**

Each phase's notes list its own open points in more detail.

## Other documents

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the parts connect |
| [docs/ROADMAP.md](docs/ROADMAP.md) | The nine phases and their goals |
| [docs/BRANCHING.md](docs/BRANCHING.md) | How branches are used |
| [docs/RUBRIC.md](docs/RUBRIC.md) | The scoring rules |
| [docs/PERSONAS.md](docs/PERSONAS.md) | The pretend users and their scenarios |
| [docs/RELATED_WORK.md](docs/RELATED_WORK.md) | Existing research and what is new here |
| [docs/MirrorGuard_Project_Document.docx](docs/MirrorGuard_Project_Document.docx) | The original project plan |

## Ethics

- All test users are synthetic. No real patient data is used.
- MirrorGuard gives risk levels. It never diagnoses anyone.
- It is a safety layer, not a replacement for a therapist or a crisis service.
- Check the crisis helpline details in the policy for your country before going live.
