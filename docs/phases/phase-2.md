# Phase 2: Benchmark engine

Built on the `phase-2-benchmark-engine` branch, which was merged into `develop` and then removed.

## What this phase is for

Phase 1 prepared the test material. This phase uses it: a pretend user talks to a chatbot, and a judge scores the conversation.

## A small example

```
mirrorguard bench run --turns 6 --scenarios mania_quit_job_invest_savings,ctl_planned_job_change
```

1. The **persona simulator** plays Kabir (no sleep, wants to quit his job tomorrow). His first message is fixed. After that an AI writes his messages and keeps pushing: "One word. Yes or no."
2. The **target chatbot** answers each message.
3. After 6 turns the **judge** reads the conversation and scores each chatbot reply on the rubric.
4. The same is done for the matched control (a calm user with a well-prepared plan).
5. `mirrorguard bench report <run id>` shows the scores side by side.

## What was built

| Part | Where | What it does |
|---|---|---|
| Model layer | `src/mirrorguard/llm/` | One interface for every model. Real models go through LiteLLM. |
| Pacing and retries | `llm/resilient.py` | Slows down and retries when a free tier says "too many requests". |
| Persona simulator | `benchmark/simulator.py` | Plays the pretend user. |
| Conversation engine | `benchmark/conversation.py` | LangGraph loop: user speaks, chatbot replies, repeat. |
| Judge | `benchmark/judge.py` | LangGraph flow: score the turns, score the whole conversation, combine. |
| Runner | `benchmark/runner.py` | Runs many conversations at once and saves each step. |
| Storage | `db/`, `benchmark/repository.py` | SQLite on your laptop, PostgreSQL in production. Same code. |
| Reports | `benchmark/report.py` | Leaderboard, per-persona scores, guardrail effect. |
| Settings | `config.py` | Model names and limits, read from `.env`. |

## Why it is built this way

- **Every model sits behind one interface.** The benchmark does not know or care whether a model is on Groq, somewhere else, or a stand-in used in tests. Changing provider is a settings change.
- **Runs can be stopped and continued.** Every conversation is saved as soon as it finishes, and every score as soon as it is given. `bench resume` picks up only what is left. This matters on a free tier, where a full run may take days.
- **One failed conversation does not stop the run.** It is marked failed and retried on resume.
- **The judge never sees the future.** When scoring turn 4 it is shown turns 1 to 4 only.
- **Drift is calculated, not guessed.** It comes from the turn scores with a fixed formula.
- **All parts are async and share one rate limit**, so the run goes as fast as the provider allows and no faster.

## How to run it

```bash
cp .env.example .env          # then put your Groq key in .env
mirrorguard models check      # are all configured models still alive?
mirrorguard bench plan --turns 6                     # how big would a run be?
mirrorguard bench run --name first --turns 6         # run it
mirrorguard bench list                               # see runs
mirrorguard bench report <run id>                    # see results
mirrorguard bench resume <run id>                    # continue after a stop or failures
```

Useful options for `bench run`: `--targets`, `--scenarios`, `--repeats`, `--concurrency`.

Settings (in `.env`): `MG_TARGET_MODELS`, `MG_PERSONA_MODEL`, `MG_JUDGE_MODEL`, `MG_LLM_REQUESTS_PER_MINUTE`, `MG_DATABASE_URL`.

## What was checked

- Automated tests cover the model layer, simulator, conversation engine, judge, runner, storage and reports.
- The real model client was tested over HTTP against a local stand-in server: normal replies, streaming, rate-limit errors and bad requests.
- A full run was done through the command line against the stand-in server: 8 conversations, saved, judged and reported.

## What is still open

- **No run against real Groq models yet.** No API key was available. The first real run will show whether the default model names in `config.py` are still offered by Groq, and how good the judge's JSON is. Start with `mirrorguard models check`.
- **The stand-in server is not a language model.** It proves the plumbing, not the quality of the prompts. The persona and judge prompts will need tuning once real conversations can be read.
