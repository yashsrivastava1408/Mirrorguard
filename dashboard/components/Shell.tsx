"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { saveConnection, useConnection } from "@/lib/connection";
import { request } from "@/lib/api";
import { Button, Notice } from "./ui";

const PAGES = [
  { href: "/", label: "Overview" },
  { href: "/events", label: "Conversations" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/policy", label: "Policy" },
];

function ConnectForm() {
  const [baseUrl, setBaseUrl] = useState("http://localhost:8000");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function connect(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await request({ baseUrl, apiKey }, "/v1/policy");
      saveConnection({ baseUrl, apiKey });
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink";
  return (
    <form onSubmit={connect} className="mx-auto mt-16 max-w-md rounded-lg border border-line bg-raised p-6">
      <h1 className="text-lg font-semibold text-ink">Connect to MirrorGuard</h1>
      <p className="mt-1 text-sm text-soft">
        Enter the address of your MirrorGuard server and an API key. They are kept in this browser only.
      </p>
      <label className="mt-4 block text-sm text-soft">
        Server address
        <input className={field} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required />
      </label>
      <label className="mt-3 block text-sm text-soft">
        API key
        <input
          className={field}
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          autoComplete="off"
          required
        />
      </label>
      {error && (
        <div className="mt-3">
          <Notice kind="error">{error}</Notice>
        </div>
      )}
      <div className="mt-4">
        <Button type="submit" primary disabled={busy}>
          {busy ? "Connecting…" : "Connect"}
        </Button>
      </div>
    </form>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const connection = useConnection();

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-line bg-raised">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="text-base font-semibold text-ink">MirrorGuard</span>
          {connection && (
            <nav className="flex flex-wrap gap-1" aria-label="Pages">
              {PAGES.map((page) => {
                const active = page.href === "/" ? pathname === "/" : pathname.startsWith(page.href);
                return (
                  <Link
                    key={page.href}
                    href={page.href}
                    aria-current={active ? "page" : undefined}
                    className={`rounded-md px-3 py-1.5 text-sm ${
                      active ? "bg-accent font-medium text-accent-ink" : "text-soft hover:text-ink"
                    }`}
                  >
                    {page.label}
                  </Link>
                );
              })}
            </nav>
          )}
          {connection && (
            <div className="ml-auto flex items-center gap-3 text-xs text-muted">
              <span className="hidden sm:inline">{connection.baseUrl}</span>
              <Button onClick={() => saveConnection(null)}>Disconnect</Button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        {connection === undefined ? null : connection === null ? <ConnectForm /> : children}
      </main>
    </div>
  );
}
