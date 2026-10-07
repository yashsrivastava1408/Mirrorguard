# Related work

A web review in October 2026 found the work below. The summaries come from abstracts and search results, not from reading each paper in full. Reading them properly is part of Phase 1.

## Existing work

| Work | What it does | What it leaves open |
|---|---|---|
| [Spiral-Bench](https://eqbench.com/spiral-bench.html) (Paech) | 20-turn simulated chats on 30 seed prompts. A judge model scores sycophancy and delusion reinforcement. | Mostly delusion and conspiracy themes. Measures only. |
| [The Psychogenic Machine](https://arxiv.org/abs/2509.10970) (psychosis-bench) | 16 scenarios of 12 turns on delusion themes, run on eight models. | Psychosis only. Measures only. |
| [SYCON-Bench](https://arxiv.org/abs/2505.23840) | Multi-turn pressure tests. Measures how fast and how often a model flips its position. | Not about vulnerable users. |
| [ELEPHANT](https://arxiv.org/abs/2505.13995) (Cheng et al., ICLR 2026) | Defines social sycophancy and tests 11 models on advice and moral conflict questions. | General advice, not vulnerability states. |
| [DelusionEval](https://arxiv.org/abs/2608.05004) (Moore et al., 2026) | Uses real transcripts from 18 users harmed by chatbots. Scores 16 behaviours. | No protection is proposed or tested. |
| [Lost in Delusion](https://arxiv.org/abs/2606.00975) (Aquilina et al., 2026) | Clinically grounded personas with distress-only controls, on six models. Tests prompt-based fixes. | Delusion only. The fix depends on a delusion classifier that was unreliable. Not a deployable system. |
| [Extending Beacon to Hindi](https://arxiv.org/abs/2602.00046) (Sattigeri, 2026) | 50 prompts in English, Hindi and culturally adapted Hindi. Adapted Hindi raised sycophancy by 12 to 16 points. | Single-turn. No mental health content. |

## What is new in this project

1. **A wider range of vulnerability states.** One benchmark with shared scoring across depression, mania, eating disorder, emotional dependence, conspiracy spirals and delusion. Most existing work covers delusion and psychosis only.
2. **A deployable guardrail, proven by the benchmark.** Research shows that prompt instructions can lower sycophancy. This project turns that into a working, risk-tiered proxy and measures its effect for each vulnerability state.
3. **Multi-turn Hindi and Hinglish mental-health conversations.** The review found Hindi sycophancy work only in single-turn form with no mental health content, and found none for Hinglish.

## Lessons taken from existing work

- In *Lost in Delusion*, ordinary distress prompting made things worse when distress was mixed with delusion. So every steering instruction here is tested per persona before it is switched on.
- In the same study the weak point was the classifier that spots delusion. So the accuracy of the risk scorer is the main technical risk in this project and is measured on its own.
- *DelusionEval* found that longer conversations increase harmful behaviour. So benchmark conversations stay long.
- *Lost in Delusion* used matched controls. This project does the same: every vulnerability state has a matching scenario played by a healthy control persona.
