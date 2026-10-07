// Where the dashboard finds the MirrorGuard API. Kept in this browser only.

import { useSyncExternalStore } from "react";

export type Connection = { baseUrl: string; apiKey: string };

const KEY = "mirrorguard.connection";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function saveConnection(connection: Connection | null) {
  try {
    if (connection) window.localStorage.setItem(KEY, JSON.stringify(connection));
    else window.localStorage.removeItem(KEY);
  } catch {
    // Storage can be blocked (private windows). The page then asks again next time.
  }
  listeners.forEach((listener) => listener());
}

export function parseConnection(raw: string | null): Connection | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    return value?.baseUrl && value?.apiKey ? value : null;
  } catch {
    return null;
  }
}

/** `undefined` while the page is still loading, `null` when not connected. */
export function useConnection(): Connection | null | undefined {
  const raw = useSyncExternalStore<string | null | undefined>(subscribe, read, () => undefined);
  return raw === undefined ? undefined : parseConnection(raw);
}
