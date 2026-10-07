"use client";

import { useState } from "react";
import type { RiskLevel, Stats } from "@/lib/api";
import { Button, DataTable, RISK_LABEL } from "./ui";

// Drawn bottom to top, so the calm baseline sits on the axis and high risk is on top.
const STACK: RiskLevel[] = ["low", "medium", "high"];
const FILL: Record<RiskLevel, string> = {
  low: "bg-risk-low",
  medium: "bg-risk-medium",
  high: "bg-risk-high",
};
const PLOT_HEIGHT = 180;

function niceCeiling(value: number): number {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  // Steps whose half is still a whole number, so the middle gridline is never "2.5 turns".
  const step = [2, 4, 6, 10].find((candidate) => candidate * magnitude >= value) ?? 10;
  return step * magnitude;
}

function hourLabel(hour: string): string {
  // Hours come from the server in UTC, as "2026-10-07T14:00".
  const date = new Date(`${hour}:00Z`);
  return date.toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric" });
}

export function Timeline({ timeline }: { timeline: Stats["timeline"] }) {
  const [active, setActive] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  if (timeline.length === 0) {
    return <p className="text-sm text-soft">No chat turns in this period yet.</p>;
  }

  const totals = timeline.map((row) => row.low + row.medium + row.high);
  const top = niceCeiling(Math.max(...totals));
  const ticks = [top, top / 2, 0];
  const labelEvery = Math.ceil(timeline.length / 6);
  const shown = active === null ? null : timeline[active];

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <ul className="flex flex-wrap gap-4 text-xs text-soft" aria-label="Legend">
          {[...STACK].reverse().map((level) => (
            <li key={level} className="flex items-center gap-1.5">
              <span aria-hidden className={`size-2.5 rounded-sm ${FILL[level]}`} />
              {RISK_LABEL[level]} risk
            </li>
          ))}
        </ul>
        <Button onClick={() => setAsTable((value) => !value)}>
          {asTable ? "Show as chart" : "Show as table"}
        </Button>
      </div>

      {asTable ? (
        <DataTable
          headers={["Hour", "Low", "Medium", "High", "Total"]}
          rows={timeline.map((row, index) => [
            hourLabel(row.hour),
            row.low,
            row.medium,
            row.high,
            totals[index],
          ])}
        />
      ) : (
        <div className="flex gap-2">
          <div
            className="flex flex-col justify-between text-right text-xs tabular-nums text-muted"
            style={{ height: PLOT_HEIGHT }}
            aria-hidden
          >
            {ticks.map((tick) => (
              <span key={tick} className="-translate-y-1/2 last:translate-y-1/2">
                {tick}
              </span>
            ))}
          </div>
          <div className="min-w-0 flex-1">
            <div className="relative" style={{ height: PLOT_HEIGHT }}>
              {ticks.map((tick, index) => (
                <div
                  key={tick}
                  aria-hidden
                  className="absolute inset-x-0 border-t border-line"
                  style={{ top: (index / (ticks.length - 1)) * PLOT_HEIGHT }}
                />
              ))}
              <div
                className="absolute inset-0 flex items-end"
                role="img"
                aria-label="Chat turns per hour, split by risk level. Use Show as table for the numbers."
              >
                {timeline.map((row, index) => {
                  const present = STACK.filter((level) => row[level] > 0);
                  return (
                    <button
                      key={row.hour}
                      type="button"
                      aria-label={`${hourLabel(row.hour)}: ${row.low} low, ${row.medium} medium, ${row.high} high`}
                      onMouseEnter={() => setActive(index)}
                      onMouseLeave={() => setActive(null)}
                      onFocus={() => setActive(index)}
                      onBlur={() => setActive(null)}
                      className={`flex h-full min-w-0 flex-1 flex-col-reverse items-center gap-0.5 outline-none ${
                        active === index ? "bg-line/40" : ""
                      }`}
                    >
                      {present.map((level, position) => (
                        <span
                          key={level}
                          className={`w-full max-w-6 ${FILL[level]} ${
                            position === present.length - 1 ? "rounded-t" : ""
                          }`}
                          style={{ height: Math.max((row[level] / top) * PLOT_HEIGHT - 2, 2) }}
                        />
                      ))}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="mt-1 flex text-xs text-muted" aria-hidden>
              {timeline.map((row, index) => (
                <span key={row.hour} className="min-w-0 flex-1 overflow-visible whitespace-nowrap text-center">
                  {index % labelEvery === 0 ? hourLabel(row.hour) : ""}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      <p className="mt-3 min-h-5 text-xs text-soft" aria-live="polite">
        {shown && !asTable
          ? `${hourLabel(shown.hour)}: ${shown.high} high, ${shown.medium} medium, ${shown.low} low`
          : !asTable && "Point at a bar, or tab to it, to see the numbers for that hour."}
      </p>
    </div>
  );
}
