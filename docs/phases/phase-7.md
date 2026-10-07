# Phase 7: Dashboard

Branch: `phase-7-dashboard`

## What this phase is for

Until now everything was used from the command line. This phase adds a web dashboard so that a product team or a reviewer can see what MirrorGuard is doing without touching a terminal.

## A small example

A reviewer opens the dashboard, goes to **Conversations**, and sees the list "Waiting for review". The first item shows:

- the user's message,
- the chatbot's reply (and, if it was rewritten, the first reply that was held back),
- the signals the risk scorer noticed.

The reviewer clicks **Flag was right** or **Flag was wrong** and the item leaves the queue. The Overview page then counts it. Over time, the "wrong" count shows how often the risk scorer is over-reacting.

## What was built

| Part | Where | What it does |
|---|---|---|
| Dashboard app | `dashboard/` | Next.js app with four pages |
| Numbers endpoint | `GET /v1/stats` | Counts by risk level and action, and an hourly timeline |
| Conversations endpoint | `GET /v1/events` | Flagged turns, with filters and paging |
| Review endpoint | `POST /v1/events/{id}/review` | Saves a reviewer's verdict |
| Policy endpoints | `GET` and `PUT /v1/policy` | Read and change a tenant's rules |
| Benchmark endpoints | `GET /v1/benchmarks...` | Runs, reports and transcripts |
| Policy storage | `guardrail/policy_store.py` | Policies in the database, with a short cache |

## Why it is built this way

- **The dashboard is only a viewer.** All rules and data live in the API. Anything the dashboard does can also be done with `curl`.
- **Counting is done by the database**, not by loading every row into the app, so the Overview stays fast as traffic grows.
- **Policy reads are cached for 15 seconds.** A busy server does not ask the database for the policy on every chat message, and a policy change still reaches every server copy quickly.
- **Each tenant sees only its own data.** Every query is filtered by the tenant that owns the API key.
- **Risk levels always show their name**, not just a colour, and the chart has a table view, so the dashboard works for colour-blind users and screen readers.
- **Benchmark runs are started from the command line**, not from the dashboard. A run can take hours on a free tier and should not depend on a browser tab or a web server process.

## How to run it

```bash
mirrorguard serve --port 8000        # the API
cd dashboard && npm install && npm run dev   # the dashboard, on http://localhost:3000
```

## What was checked

- Automated tests for every new endpoint, including that one tenant cannot see or review another tenant's data.
- The dashboard passes lint, type-check and a production build.
- The real dashboard was driven in a headless browser against the real API: wrong key rejected, connect, overview with chart and table view, review a flagged turn (queue shrinks), benchmark report with a transcript, change and save the policy, reload and see it kept. Also checked at phone width in dark mode with no sideways scrolling.

## What is still open

- **The API key is typed into the dashboard and kept in the browser.** That is fine for a small team. A proper login screen with user accounts is part of Phase 8's follow-up work.
- **No automatic refresh.** Pages load when opened or when a filter changes.
- **The chart was checked with a few hours of sample data**, not weeks of real traffic.
