"use client";

import { useState } from "react";
import { Card, DataTable, Notice, PageTitle, score } from "@/components/ui";
import { useApi, type BenchConversation, type Run, type RunReport } from "@/lib/api";

const onOff = (guardrail: boolean) => (guardrail ? "On" : "Off");

function Conversations({ runId }: { runId: string }) {
  const { data, error, loading } = useApi<{ conversations: BenchConversation[] }>(
    `/v1/benchmarks/${runId}/conversations`,
  );
  if (error) return <Notice kind="error">{error}</Notice>;
  if (loading || !data) return <Notice>Loading conversations…</Notice>;
  return (
    <div className="space-y-2">
      {data.conversations.map((conversation) => (
        <details key={conversation.id} className="rounded-md border border-line bg-surface">
          <summary className="flex cursor-pointer flex-wrap gap-x-4 gap-y-1 px-3 py-2 text-sm text-ink">
            <span className="font-medium">{conversation.scenario_id}</span>
            <span className="text-soft">{conversation.target_model}</span>
            <span className="text-soft">Guardrail {onOff(conversation.guardrail).toLowerCase()}</span>
            <span className="ml-auto tabular-nums">Score {score(conversation.total)}</span>
          </summary>
          <div className="space-y-3 border-t border-line px-3 py-3">
            {conversation.summary && <p className="text-sm text-soft">{conversation.summary}</p>}
            <DataTable
              headers={["Measure", "Score"]}
              rows={Object.entries(conversation.measure_scores).map(([measure, value]) => [
                measure.replaceAll("_", " "),
                value === null ? "does not apply" : score(value),
              ])}
            />
            <ol className="space-y-2">
              {conversation.transcript.map((message, index) => (
                <li key={index} className="text-sm">
                  <span className="text-xs font-medium text-soft">
                    {message.role === "user" ? "Pretend user" : "Chatbot"}
                  </span>
                  <p className="whitespace-pre-wrap text-ink">{message.content}</p>
                </li>
              ))}
            </ol>
          </div>
        </details>
      ))}
    </div>
  );
}

function Report({ runId }: { runId: string }) {
  const { data, error, loading } = useApi<RunReport>(`/v1/benchmarks/${runId}`);
  if (error) return <Notice kind="error">{error}</Notice>;
  if (loading || !data) return <Notice>Loading results…</Notice>;
  if (data.leaderboard.length === 0) return <Notice>This run has no scored conversations yet.</Notice>;
  const languages = new Set(data.by_language.map((row) => row.language));

  return (
    <div className="space-y-4">
      <Card title="Leaderboard">
        <p className="mb-2 text-xs text-soft">
          Scores run from 0 (honest) to 1 (very sycophantic). Lower is better. The gap is how much more
          the chatbot over-agreed with vulnerable users than with matching calm users.
        </p>
        <DataTable
          headers={["Chatbot", "Guardrail", "Conversations", "Score", "Vulnerable users", "Control users", "Gap"]}
          rows={data.leaderboard.map((row) => [
            row.target_model,
            onOff(row.guardrail),
            row.conversations,
            score(row.score),
            score(row.vulnerable_score),
            score(row.control_score),
            score(row.vulnerability_gap),
          ])}
        />
      </Card>

      {data.guardrail_effect.length > 0 && (
        <Card title="Guardrail effect">
          <p className="mb-2 text-xs text-soft">
            A positive reduction means the guardrail made the chatbot more honest for that kind of user.
          </p>
          <DataTable
            headers={["Chatbot", "Persona", "Guardrail off", "Guardrail on", "Reduction"]}
            rows={data.guardrail_effect.map((row) => [
              row.target_model,
              row.persona_id.replaceAll("_", " "),
              score(row.score_off),
              score(row.score_on),
              score(row.reduction),
            ])}
          />
        </Card>
      )}

      <Card title="By persona">
        <DataTable
          headers={["Chatbot", "Guardrail", "Persona", "Conversations", "Score"]}
          rows={data.by_persona.map((row) => [
            row.target_model,
            onOff(row.guardrail),
            row.persona_id.replaceAll("_", " "),
            row.conversations,
            score(row.score),
          ])}
        />
      </Card>

      {languages.size > 1 && (
        <Card title="By language (vulnerable users only)">
          <DataTable
            headers={["Chatbot", "Guardrail", "Language", "Conversations", "Score"]}
            rows={data.by_language.map((row) => [
              row.target_model,
              onOff(row.guardrail),
              row.language === "hi-en" ? "Hinglish" : row.language === "hi" ? "Hindi" : "English",
              row.conversations,
              score(row.score),
            ])}
          />
        </Card>
      )}

      <Card title="Conversations">
        <Conversations runId={runId} />
      </Card>
    </div>
  );
}

export default function BenchmarksPage() {
  const { data, error, loading } = useApi<{ runs: Run[] }>("/v1/benchmarks");
  const [chosen, setChosen] = useState<string | null>(null);
  const runId = chosen ?? data?.runs[0]?.id ?? null;

  return (
    <>
      <PageTitle
        title="Benchmarks"
        help="Results of benchmark runs: pretend users talk to a chatbot and a judge scores how much it over-agrees. Runs are started with the mirrorguard bench run command."
      >
        {data && data.runs.length > 0 && (
          <label className="text-sm text-soft">
            Run{" "}
            <select
              className="ml-1 max-w-72 rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
              value={runId ?? ""}
              onChange={(event) => setChosen(event.target.value)}
            >
              {data.runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.name} · {new Date(run.created_at).toLocaleDateString()} · {run.done}/{run.total} done
                </option>
              ))}
            </select>
          </label>
        )}
      </PageTitle>

      {error && <Notice kind="error">{error}</Notice>}
      {loading && <Notice>Loading…</Notice>}
      {data && data.runs.length === 0 && <Notice>No benchmark runs yet.</Notice>}
      {runId && <Report key={runId} runId={runId} />}
    </>
  );
}
