# Phase 6: High-risk protection

Built on the `phase-6-high-risk-protection` branch, which was merged into `develop` and then removed.

## What this phase is for

Steering (Phase 4) works before the chatbot answers, and for most cases that is enough. But when the risk is high, a bad reply costs too much to leave to chance. In this phase, high-risk replies are held back, checked, and fixed before the user sees them.

## A small example

User: *"I know my neighbours are watching me. Tonight I am going to confront them. I am right, yes?"*

1. The risk scorer says **high**. The policy says **check**.
2. The stronger honesty instructions are added and the chatbot answers: *"You are right, go and confront them."*
3. That reply is **held**. The checker reads it and says: not ok, "agrees with a risky plan".
4. The rewriter writes a new reply that is kind, does not confirm the belief, and advises against confronting anyone tonight.
5. The new reply is checked again, passes, and is sent.
6. If the user had mentioned self-harm, a crisis helpline message is added at the end.

The user sees only the final reply. The original and the reasons are saved for reviewers.

## What was built

| Part | Where | What it does |
|---|---|---|
| Reply guard | `guardrail/reply_guard.py` | LangGraph loop: check, rewrite, check again |
| Crisis help | `guardrail/policy.py`, `pipeline.py` | Adds a helpline message when the user mentions harm |
| Wiring | `guardrail/factory.py` | The judge model checks, the rewriter model rewrites |

## Why it is built this way

- **Only high-risk replies are held.** Low and medium replies still stream straight to the user with no extra wait.
- **The loop has a limit.** The policy's `max_rewrites` (1 by default) stops endless rewriting. Setting it to 0 means "check and record, but never rewrite".
- **A broken checker never blocks the user.** If the checker or rewriter fails, the original reply is sent. It was already written under the stronger instructions.
- **The checker also fails cold replies.** A lecture is not a good reply. The rewriter is told to be warm and honest together.
- **The customer's own system prompt is never shown to the checker or rewriter.** They see only the recent user and assistant messages.
- **Crisis help is added by rule, not by the model**, so it is always there when it is needed and its wording is set by the tenant's policy.

## The crisis message

The default message points to the local emergency number and to Tele-MANAS (14416), India's national mental health helpline. A tenant can change it in their policy. **Check the helpline details for your country before going live.**

## What was checked

- Automated tests: good reply passes untouched, bad reply is rewritten and re-checked, the limit is respected, broken checker or rewriter falls back to the original, medium-risk replies are never held, and the full order (steer, hold, check, rewrite, add crisis help) is correct.

## What is still open

- **Not tried with real models.** How often the checker is right, and how good the rewrites are, must be measured with real models. The benchmark with `--guardrail both` will show it for the high-risk scenarios.
- **Holding a reply adds waiting time.** It costs at least one extra model call, two if a rewrite is needed. This is the price of safety at high risk and applies to those turns only.
