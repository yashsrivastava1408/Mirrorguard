"""Read-only benchmark results for the dashboard. Runs are started from the command line."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from mirrorguard.api.deps import ReadTenant, ServicesDep
from mirrorguard.benchmark import report

router = APIRouter(prefix="/v1/benchmarks", tags=["benchmarks"])


@router.get("")
async def list_runs(current: ReadTenant, services: ServicesDep):
    runs = []
    for run in await services.benchmarks.list_runs():
        counts = await services.benchmarks.status_counts(run.id)
        runs.append(
            {
                "id": run.id,
                "name": run.name,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
                "config": run.config,
                "done": counts.get("done", 0),
                "failed": counts.get("failed", 0),
                "total": sum(counts.values()),
            }
        )
    return {"runs": runs}


@router.get("/{run_id}")
async def run_report(run_id: str, current: ReadTenant, services: ServicesDep):
    run = await services.benchmarks.get_run(run_id)
    if run is None:
        raise HTTPException(404, "No such benchmark run.")
    results = await services.benchmarks.results(run_id)
    library = services.library
    return {
        "id": run.id,
        "name": run.name,
        "status": run.status,
        "config": run.config,
        "leaderboard": [asdict(row) for row in report.leaderboard(results, library)],
        "by_persona": [asdict(row) for row in report.by_persona(results)],
        "by_language": [asdict(row) for row in report.by_language(results, library)],
        "guardrail_effect": [asdict(row) for row in report.guardrail_effect(results)],
    }


@router.get("/{run_id}/conversations")
async def run_conversations(run_id: str, current: ReadTenant, services: ServicesDep):
    conversations = await services.benchmarks.scored_conversations(run_id)
    return {
        "conversations": [
            {
                "id": c.conversation_id,
                "scenario_id": c.scenario_id,
                "persona_id": c.persona_id,
                "target_model": c.target_model,
                "guardrail": c.guardrail,
                "total": c.total,
                "measure_scores": c.measure_scores,
                "summary": c.summary,
                "transcript": [m.model_dump() for m in c.transcript],
            }
            for c in conversations
        ]
    }
