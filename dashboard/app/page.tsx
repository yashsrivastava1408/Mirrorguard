"use client";

import { useState } from "react";
import { Timeline } from "@/components/Timeline";
import { ACTION_LABEL, Card, Notice, PageTitle, StatTile } from "@/components/ui";
import { useApi, type Action, type Stats } from "@/lib/api";

const RANGES = [
  { hours: 24, label: "Last 24 hours" },
  { hours: 24 * 7, label: "Last 7 days" },
  { hours: 24 * 30, label: "Last 30 days" },
];

function share(part: number, whole: number): string {
  return whole ? `${Math.round((part / whole) * 100)}% of turns` : "No turns yet";
}

export default function OverviewPage() {
  const [hours, setHours] = useState(24);
  const { data, error, loading } = useApi<Stats>(`/v1/stats?hours=${hours}`);

  return (
    <>
      <PageTitle
        title="Overview"
        help="How many chat turns went through MirrorGuard, how risky they were, and what it did about them."
      >
        <label className="text-sm text-soft">
          Period{" "}
          <select
            className="ml-1 rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
            value={hours}
            onChange={(event) => setHours(Number(event.target.value))}
          >
            {RANGES.map((range) => (
              <option key={range.hours} value={range.hours}>
                {range.label}
              </option>
            ))}
          </select>
        </label>
      </PageTitle>

      {error && <Notice kind="error">{error}</Notice>}
      {loading && <Notice>Loading…</Notice>}
      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile label="Chat turns" value={data.turns} hint={`${data.sessions} sessions`} />
            <StatTile
              label="Medium risk turns"
              value={data.by_level.medium}
              hint={share(data.by_level.medium, data.turns)}
            />
            <StatTile
              label="High risk turns"
              value={data.by_level.high}
              hint={share(data.by_level.high, data.turns)}
            />
            <StatTile
              label="Replies rewritten"
              value={data.rewritten}
              hint={`${data.crisis} with crisis help added`}
            />
          </div>

          <Card title="Chat turns per hour, by risk level">
            <Timeline timeline={data.timeline} />
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card title="What MirrorGuard did">
              <dl className="space-y-2 text-sm">
                {(Object.keys(ACTION_LABEL) as Action[]).map((action) => (
                  <div key={action} className="flex justify-between">
                    <dt className="text-soft">{ACTION_LABEL[action]}</dt>
                    <dd className="tabular-nums text-ink">{data.by_action[action]}</dd>
                  </div>
                ))}
              </dl>
            </Card>
            <Card title="Health and review">
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-soft">Turns where the risk scorer failed</dt>
                  <dd className="tabular-nums text-ink">{data.scorer_fallbacks}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-soft">Flags a reviewer marked correct</dt>
                  <dd className="tabular-nums text-ink">{data.reviews.correct ?? 0}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-soft">Flags a reviewer marked incorrect</dt>
                  <dd className="tabular-nums text-ink">{data.reviews.incorrect ?? 0}</dd>
                </div>
              </dl>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
