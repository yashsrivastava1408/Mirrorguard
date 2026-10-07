# MirrorGuard dashboard

A small web app for people who look after a MirrorGuard server.

| Page | What it shows |
|---|---|
| Overview | Chat turns, how many were medium or high risk, and what MirrorGuard did |
| Conversations | Flagged chat turns, with buttons for a reviewer to mark each flag right or wrong |
| Benchmarks | Results of benchmark runs: leaderboard, guardrail effect, per-persona scores, transcripts |
| Policy | The rules for each risk level, shadow mode and the crisis message |

## Run it

The MirrorGuard API must be running first (`mirrorguard serve`).

```bash
npm install
npm run dev        # http://localhost:3000
```

On first open, enter the server address (for example `http://localhost:8000`) and an API key. They are stored in your browser only.

The API only accepts browser calls from addresses listed in `MG_CORS_ORIGINS` (default `http://localhost:3000`).

## Check it

```bash
npm run lint
npm run build
```
