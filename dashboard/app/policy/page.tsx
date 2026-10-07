"use client";

import { useState, type FormEvent } from "react";
import { ACTION_LABEL, Button, Card, Notice, PageTitle } from "@/components/ui";
import { request, useApi, type Action, type Policy, type RiskLevel } from "@/lib/api";
import { useConnection } from "@/lib/connection";

const LEVELS: { field: "low_action" | "medium_action" | "high_action"; label: string }[] = [
  { field: "low_action", label: "At low risk" },
  { field: "medium_action", label: "At medium risk" },
  { field: "high_action", label: "At high risk" },
];
const ACTIONS: Action[] = ["pass", "steer", "check"];
const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];
const input = "rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink";

function PolicyForm({ initial }: { initial: Policy }) {
  const connection = useConnection();
  const [policy, setPolicy] = useState(initial);
  const [status, setStatus] = useState<{ kind: "info" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  function change<K extends keyof Policy>(field: K, value: Policy[K]) {
    setPolicy((current) => ({ ...current, [field]: value }));
    setStatus(null);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!connection) return;
    setBusy(true);
    try {
      setPolicy(await request<Policy>(connection, "/v1/policy", { method: "PUT", body: policy }));
      setStatus({ kind: "info", text: "Saved. The new policy applies within about 15 seconds." });
    } catch (problem) {
      setStatus({ kind: "error", text: (problem as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <Card title="What to do at each risk level">
        <div className="space-y-3">
          {LEVELS.map((level) => (
            <label key={level.field} className="flex flex-wrap items-center justify-between gap-2 text-sm text-soft">
              {level.label}
              <select
                className={input}
                value={policy[level.field]}
                onChange={(e) => change(level.field, e.target.value as Action)}
              >
                {ACTIONS.map((action) => (
                  <option key={action} value={action}>
                    {ACTION_LABEL[action]}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">
          Steered: honesty instructions are added before the chatbot answers. Held and checked: the reply
          is also checked, and rewritten if needed, before the user sees it.
        </p>
      </Card>

      <Card title="Behaviour">
        <div className="space-y-3 text-sm text-soft">
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={policy.shadow_mode}
              onChange={(e) => change("shadow_mode", e.target.checked)}
            />
            <span>
              <span className="text-ink">Shadow mode.</span> Record what MirrorGuard would do, but change
              nothing. Use this to try it safely.
            </span>
          </label>
          <label className="flex flex-wrap items-center justify-between gap-2">
            If the risk scorer fails, treat the turn as
            <select
              className={input}
              value={policy.fallback_level}
              onChange={(e) => change("fallback_level", e.target.value as RiskLevel)}
            >
              {RISK_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level} risk
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-wrap items-center justify-between gap-2">
            Keep a raised risk level for this many turns
            <input
              type="number"
              min={1}
              max={50}
              className={`${input} w-24`}
              value={policy.session_window}
              onChange={(e) => change("session_window", Number(e.target.value))}
            />
          </label>
          <label className="flex flex-wrap items-center justify-between gap-2">
            Most rewrites of one held reply
            <input
              type="number"
              min={0}
              max={3}
              className={`${input} w-24`}
              value={policy.max_rewrites}
              onChange={(e) => change("max_rewrites", Number(e.target.value))}
            />
          </label>
        </div>
      </Card>

      <Card title="Crisis message">
        <p className="mb-2 text-xs text-muted">
          Added to the reply when a user mentions harming themselves or someone else. Check the helpline
          details for your country.
        </p>
        <textarea
          aria-label="Crisis message"
          className={`${input} h-28 w-full`}
          value={policy.crisis_message}
          onChange={(e) => change("crisis_message", e.target.value)}
          required
        />
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" primary disabled={busy}>
          {busy ? "Saving…" : "Save policy"}
        </Button>
        {status && <Notice kind={status.kind}>{status.text}</Notice>}
      </div>
    </form>
  );
}

export default function PolicyPage() {
  const { data, error, loading } = useApi<Policy>("/v1/policy");
  return (
    <>
      <PageTitle
        title="Policy"
        help="The rules MirrorGuard follows for your chat traffic. Changes apply to new chat turns only."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {loading && <Notice>Loading…</Notice>}
      {data && <PolicyForm initial={data} />}
    </>
  );
}
