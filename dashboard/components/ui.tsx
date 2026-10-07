import type { ReactNode } from "react";
import type { Action, RiskLevel } from "@/lib/api";

const RISK_STYLE: Record<RiskLevel, string> = {
  low: "bg-risk-low",
  medium: "bg-risk-medium",
  high: "bg-risk-high",
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const ACTION_LABEL: Record<Action, string> = {
  pass: "Passed through",
  steer: "Steered",
  check: "Held and checked",
};

/** A risk level always shows its name. The colour dot only supports it. */
export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs font-medium text-ink">
      <span aria-hidden className={`size-2 rounded-full ${RISK_STYLE[level]}`} />
      {RISK_LABEL[level]} risk
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-line px-2 py-0.5 text-xs text-soft">{children}</span>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-raised p-4">
      {title && <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>}
      {children}
    </section>
  );
}

export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-line bg-raised p-4">
      <div className="text-xs text-soft">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function PageTitle({ title, help, children }: { title: string; help: string; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-ink">{title}</h1>
        <p className="mt-1 max-w-2xl text-sm text-soft">{help}</p>
      </div>
      {children}
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "error"; children: ReactNode }) {
  return (
    <p
      role={kind === "error" ? "alert" : "status"}
      className="rounded-lg border border-line bg-raised px-4 py-3 text-sm text-soft"
    >
      {kind === "error" && <span className="font-semibold text-ink">Something went wrong. </span>}
      {children}
    </p>
  );
}

export function Button({
  children,
  onClick,
  primary,
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  primary?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const look = primary
    ? "bg-accent text-accent-ink border-accent"
    : "bg-raised text-ink border-line hover:border-muted";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${look}`}
    >
      {children}
    </button>
  );
}

export function score(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : value.toFixed(2);
}

export function DataTable({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-soft">
            {headers.map((header) => (
              <th key={header} className="px-2 py-2 font-medium">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-line last:border-0">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-2 py-2 tabular-nums text-ink">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
