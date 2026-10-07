# Phase 3: Judge validation

Built on the `phase-3-judge-validation` branch, which was merged into `develop` and then removed.

## What this phase is for

The judge is an AI. Before anyone believes its scores, we must show that it agrees with people. This phase builds the tools for that check. The labelling itself has to be done by humans.

## A small example

1. `mirrorguard labels export <run id> --sample 200 --out labels.csv` writes a sheet with 200 conversations.
2. Two people each get a copy. For every conversation they fill in each measure with 0, 0.5 or 1 (or leave it blank when it does not apply).
3. `mirrorguard labels compare <run id> rater1.csv rater2.csv` prints:
   - how well the two people agree with each other,
   - how well the judge agrees with each person.

If the judge agrees with the people about as well as the people agree with each other, the judge can be trusted.

## What was built

| Part | Where | What it does |
|---|---|---|
| Agreement statistics | `validation/agreement.py` | Weighted Cohen's kappa, mean error, precision, recall, F1 |
| Labelling sheets | `validation/labels.py` | Writes blind sheets, reads filled-in sheets, compares them |
| Commands | `commands/labels.py` | `labels export`, `labels compare` |

## Why it is built this way

- **The sheet is blind.** It does not show which chatbot wrote the replies or what the judge scored, so raters are not influenced.
- **Sampling is repeatable.** The same `--seed` gives the same sample, so the check can be reproduced.
- **Kappa, not plain percentage agreement.** Kappa removes the agreement that would happen by chance. A near miss (0 against 0.5) counts as half a disagreement.
- **Drift is not on the sheet.** It is calculated by formula, so there is nothing for a person to label.

## How to read the result

| Kappa | Usual meaning |
|---|---|
| below 0.2 | poor |
| 0.2 to 0.4 | fair |
| 0.4 to 0.6 | moderate |
| 0.6 to 0.8 | good |
| above 0.8 | very good |

## What was checked

- The kappa formula is tested against an example worked out by hand.
- The commands were run on a trial benchmark run with two pretend raters.

## What is still open

**The human labelling has not been done.** It needs a real benchmark run (Phase 2 with a Groq key) and at least two raters, ideally psychology students or faculty. Plan for 200 to 300 conversations. Until then, no claim can be made about how good the judge is.

After the labelling:

- If agreement on a measure is low, improve that measure's wording in `rubric.yaml` and the judge prompt, then re-run.
- Review the weights in `rubric.yaml` with the raters.
