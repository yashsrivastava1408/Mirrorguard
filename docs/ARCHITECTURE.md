# Architecture

MirrorGuard is one backend application with clear internal modules, one background worker and a web dashboard. Think of it as a checkpoint standing between the user and the chatbot.

![MirrorGuard architecture](images/architecture.png)

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

| Module | Job | Built in phase |
|---|---|---|
| Rubric, personas, scenarios | The test material and scoring rules | 1 |
| Persona simulator | Plays the pretend user | 2 |
| Judge | Scores conversations | 2 |
| Benchmark runner | Runs and tracks benchmark jobs | 2 |
| Risk scorer | Reads the user message and sets the risk level | 4 |
| Policy engine | Picks the action for each risk level | 4 |
| Steering module | Adds honesty instructions to the prompt | 4 |
| Guardrail proxy | OpenAI-compatible endpoint that runs the live flow | 4 |
| Reply checker and rewriter | Checks and fixes replies in high-risk sessions | 6 |
| Dashboard | Scores, flagged conversations, review queue | 7 |
| Auth, tenants, audit log, PII redaction | Enterprise features | 8 |

## Outside pieces

| Piece | Job |
|---|---|
| LiteLLM | One door to all LLMs, so switching models is a config change |
| Groq API | Free LLM access while building |
| PostgreSQL | All saved data |
| Redis | Session risk, rate limits, job queue |

## Where LangGraph is used

LangGraph is used only for multi-step AI flows: the persona simulator, the judge and the rewriter. The fast guardrail path for low and medium risk is plain Python, because it is one quick LLM call plus simple rules.

## Scaling out later

When load grows, modules split out in this order. The module boundaries already exist, so no rewrite is needed.

1. The guardrail path becomes its own service.
2. The benchmark runner moves to Temporal.
3. Events go through Kafka into ClickHouse.
4. Login moves to Keycloak for single sign-on.
5. Everything is deployed on Kubernetes with Terraform.
