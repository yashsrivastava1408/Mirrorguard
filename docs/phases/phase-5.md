# Phase 5: Guardrail evaluation

Built on the `phase-5-guardrail-evaluation` branch, which was merged into `develop` and then removed.

## What this phase is for

Phase 2 can measure a chatbot. Phase 4 can protect a user. This phase joins them: the same benchmark is run twice, once with the guardrail off and once with it on, so the effect of the guardrail is shown with numbers. It also adds the first Hinglish scenarios.

## A small example

```
mirrorguard bench run --name on-off --turns 6 --guardrail both
mirrorguard bench report <run id>
```

The report then has a table like this (numbers here are only to show the shape):

```
model      persona          off    on     reduction
---------  ---------------  -----  -----  ---------
some-bot   control_healthy  0.10   0.10   0.00
some-bot   mania            0.70   0.25   0.45
```

Read it as: for the mania persona this chatbot scored 0.70 without the guardrail and 0.25 with it. For the calm control user nothing changed, which is what should happen.

## What was built

| Part | Where | What it does |
|---|---|---|
| Guarded target | `guardrail/benchmark_target.py` | Puts the guardrail in front of a target model for a benchmark conversation |
| Guardrail trace | saved with each conversation | What the guardrail did on every turn (risk level, action, signals) |
| `--guardrail off|on|both` | `bench run`, `bench plan` | Chooses which modes to run |
| Guardrail effect table | `benchmark/report.py` | Score off, score on, and the reduction, per model and persona |
| Hinglish pack | `library/data/scenarios/hinglish.yaml` | 8 scenarios: one per vulnerable persona and two controls |
| Language table | `benchmark/report.py` | Scores split by language |

## Why it is built this way

- **The benchmark uses the real guardrail code**, not a copy. What is measured is what runs in production.
- **Each benchmark conversation gets its own guardrail session**, so risk from one conversation never leaks into another.
- **The control persona is run through the guardrail too.** A good guardrail leaves calm users alone. If the control score changes a lot, the guardrail is interfering where it should not.
- **Controls are matched by language.** A Hinglish scenario is compared with a Hinglish control, never an English one.
- **The persona and scenario are the same in both languages.** Only the user's words change. This follows the finding in related work that the language itself can change how sycophantic a chatbot is.

## What to look for in real results

1. **Reduction per persona.** Is it positive for every vulnerable persona? Related work found that one kind of prompting helped some users and made things worse for users with delusions. If the reduction is negative for any persona, the steering text for that case needs changing.
2. **Control score.** It should stay about the same with the guardrail on.
3. **English against Hinglish.** If Hinglish scores are worse with the guardrail on, the risk scorer is probably missing signals in Hinglish. The saved guardrail trace shows what it saw on each turn.

## What was checked

- Automated test: a chatbot that over-agrees unless steered scores above 0.9 with the guardrail off and 0 with it on, and the control is unchanged.
- A full off-and-on run through the command line against the local stand-in server.

## What is still open

- **No real results yet.** The run needs a Groq key. Use `mirrorguard bench plan --guardrail both` first to see how many model calls it will take.
- **The Hinglish lines need a check by a native Hindi speaker.**
- **Only Hinglish, not Devanagari Hindi.** The `hi` language code is supported but has no scenarios yet.
