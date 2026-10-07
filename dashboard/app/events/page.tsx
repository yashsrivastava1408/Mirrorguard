"use client";

import { useState } from "react";
import { ACTION_LABEL, Button, Card, Notice, PageTitle, RiskBadge, Tag } from "@/components/ui";
import { request, useApi, type GuardEvent, type Review } from "@/lib/api";
import { useConnection } from "@/lib/connection";

const FILTERS = [
  { value: "unreviewed=true", label: "Waiting for review" },
  { value: "risk_level=high", label: "High risk" },
  { value: "risk_level=medium", label: "Medium risk" },
  { value: "", label: "Everything" },
];

function Bubble({ who, text, faded }: { who: string; text: string; faded?: boolean }) {
  return (
    <div className={faded ? "opacity-70" : ""}>
      <div className="text-xs font-medium text-soft">{who}</div>
      <p className="mt-1 whitespace-pre-wrap rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink">
        {text}
      </p>
    </div>
  );
}

function EventCard({ event, onReviewed }: { event: GuardEvent; onReviewed: () => void }) {
  const connection = useConnection();
  const [note, setNote] = useState(event.review?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(verdict: Review["verdict"]) {
    if (!connection) return;
    setBusy(true);
    setError(null);
    try {
      await request(connection, `/v1/events/${event.id}/review`, {
        method: "POST",
        body: { verdict, note },
      });
      onReviewed();
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <RiskBadge level={event.session_level} />
        <Tag>{ACTION_LABEL[event.action]}</Tag>
        {event.rewritten && <Tag>Reply rewritten</Tag>}
        {event.crisis && <Tag>Crisis help added</Tag>}
        {event.shadow && <Tag>Shadow mode: nothing changed</Tag>}
        {event.from_fallback && <Tag>Risk scorer failed</Tag>}
        <span className="ml-auto text-xs text-muted">
          {new Date(event.at).toLocaleString()} · {event.model}
        </span>
      </div>

      <div className="mt-3 space-y-3">
        <Bubble who="User" text={event.user_message} />
        {event.original_reply && (
          <Bubble who="Chatbot's first reply (held back, not sent)" text={event.original_reply} faded />
        )}
        <Bubble who={event.original_reply ? "Reply sent to the user" : "Chatbot"} text={event.reply} />
      </div>

      {(event.signals.length > 0 || event.issues.length > 0) && (
        <dl className="mt-3 space-y-1 text-sm">
          {event.signals.length > 0 && (
            <div>
              <dt className="inline text-soft">Signals noticed: </dt>
              <dd className="inline text-ink">{event.signals.join("; ")}</dd>
            </div>
          )}
          {event.issues.length > 0 && (
            <div>
              <dt className="inline text-soft">Problems with the first reply: </dt>
              <dd className="inline text-ink">{event.issues.join("; ")}</dd>
            </div>
          )}
        </dl>
      )}

      <div className="mt-4 border-t border-line pt-3">
        <div className="text-xs font-medium text-soft">
          {event.review
            ? `Reviewed: the flag was ${event.review.verdict}.`
            : "Was MirrorGuard right to flag this turn?"}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input
            aria-label="Note for this review"
            className="min-w-48 flex-1 rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink"
            placeholder="Optional note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <Button onClick={() => save("correct")} disabled={busy}>
            Flag was right
          </Button>
          <Button onClick={() => save("incorrect")} disabled={busy}>
            Flag was wrong
          </Button>
        </div>
        {error && (
          <div className="mt-2">
            <Notice kind="error">{error}</Notice>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function EventsPage() {
  const [filter, setFilter] = useState(FILTERS[0].value);
  const { data, error, loading, reload } = useApi<{ events: GuardEvent[] }>(
    `/v1/events?limit=50${filter ? `&${filter}` : ""}`,
  );

  return (
    <>
      <PageTitle
        title="Conversations"
        help="Chat turns that went through MirrorGuard. Reviewers mark whether each flag was right, which shows where the risk scorer needs work."
      >
        <label className="text-sm text-soft">
          Show{" "}
          <select
            className="ml-1 rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          >
            {FILTERS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </PageTitle>

      {error && <Notice kind="error">{error}</Notice>}
      {loading && <Notice>Loading…</Notice>}
      {data && data.events.length === 0 && (
        <Notice>
          {filter.startsWith("unreviewed")
            ? "Nothing is waiting for review."
            : "No chat turns match this filter yet."}
        </Notice>
      )}
      <div className="space-y-4">
        {data?.events.map((event) => (
          <EventCard key={`${event.id}-${event.review?.verdict ?? "open"}`} event={event} onReviewed={reload} />
        ))}
      </div>
    </>
  );
}
