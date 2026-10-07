# Phase 9: Deployment

Branch: `phase-9-deploy`

## What this phase is for

Everything so far ran on a laptop with a local file as the database. This phase adds what is needed to run MirrorGuard as a real service: a proper database with migrations, containers, one command to start the whole system, automatic checks on every push, and a load test.

## A small example

On a server with Docker:

```bash
cp .env.example .env        # fill in GROQ_API_KEY and POSTGRES_PASSWORD
docker compose up --build
```

This starts five things in order:

1. **PostgreSQL**, the database.
2. **Redis**, for session risk and rate limits.
3. **migrate**, which brings the database up to date and then exits.
4. **api**, the MirrorGuard server, on port 8000.
5. **dashboard**, on port 3000.

Then create a tenant and a key inside the running API container:

```bash
docker compose exec api mirrorguard tenants create acme --name "Acme Ltd"
docker compose exec api mirrorguard keys create acme --role admin
```

## What was built

| Part | Where | What it does |
|---|---|---|
| Migrations | `src/mirrorguard/migrations/`, `mirrorguard db migrate` | Creates and updates database tables in a controlled way |
| API image | `Dockerfile` | Small image, runs as a non-root user, has a health check |
| Dashboard image | `dashboard/Dockerfile` | Production build of the dashboard |
| Whole system | `docker-compose.yml` | Database, cache, migration step, API, dashboard |
| Settings template | `.env.example` | Every setting, with comments |
| Automatic checks | `.github/workflows/ci.yml` | Lint, format check, tests, dashboard build on every push |
| Load test | `scripts/loadtest.js` | k6 script for the guardrail endpoint |
| Server command | `mirrorguard serve --workers N` | Runs several server processes |

## How it scales

| When this grows | Do this |
|---|---|
| More chat traffic | Run more API copies (`--workers`, or `docker compose up --scale api=3` behind a load balancer). Copies share nothing in memory: session risk and rate limits are in Redis. |
| More stored events | PostgreSQL with the indexes already defined. Run `mirrorguard retention purge` daily. |
| Bigger benchmarks | Raise `MG_BENCHMARK_CONCURRENCY` and the rate limit settings as your provider allows. Runs resume where they stopped. |
| Much more of everything | The split described in `docs/ARCHITECTURE.md`: guardrail as its own service, Kafka and ClickHouse for events, Temporal for benchmarks. |

## What was checked

These were run for real on this machine, with a temporary PostgreSQL and Redis:

- **Migrations on PostgreSQL**: `db migrate` created all tables. Running it a second time changed nothing.
- **Two server processes sharing state**: a session marked medium risk stayed medium across five requests spread over both processes, which proves the risk level lives in Redis and not in one process's memory.
- **Numbers endpoint on PostgreSQL**, including the hourly timeline. This found and fixed a real bug: hours were grouped in the database's local time zone instead of UTC.
- **Masking on the way to storage**: a phone number in a chat message was saved as `[PHONE]`.
- **A benchmark run stored in PostgreSQL**, with the guardrail off and on.
- **Load test with k6**: 20 simulated users for 15 seconds through two server processes. About 4,100 requests, none failed, every one saved. Replies took about 60 ms in the middle case and about 135 ms for the slowest 5%.

### How to read the load test

The model behind MirrorGuard in this test was a local stand-in that answers instantly. So the 60 ms is MirrorGuard's **own** cost per turn: checking the key, the rate limit, two model calls through LiteLLM (risk scorer and chatbot), Redis, and queuing the event. With a real model, the wait a user feels will be this plus the time the risk model and the chatbot take, which will be much larger than 60 ms. The earlier design goal of "under 500 ms added delay" therefore depends on how fast the risk model is, and **has not been measured with a real model**.

## What is still open

- **The Docker images and `docker compose up` were not built or run.** Docker was not running on this machine. The files were written carefully but are untested. Expect to fix small things on the first build.
- **The CI workflow has not run**, because the project is not on GitHub yet.
- **Nothing is deployed to a server.** Choosing a host, a domain and HTTPS is still to do. HTTPS must be added in front of the API (for example with Caddy or a cloud load balancer). Never expose port 8000 directly to the internet.
- **No backups are set up.** Use your host's PostgreSQL backups, or a daily `pg_dump`.
- **No monitoring is wired in.** `/healthz` exists for a load balancer. Metrics and tracing (Prometheus, OpenTelemetry, Langfuse) are in the plan but not built.
- **The automated tests use SQLite.** PostgreSQL was checked by the real run described above, not by the test suite.
