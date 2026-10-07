import { useCallback, useEffect, useState } from "react";
import { Connection, useConnection } from "./connection";

export type RiskLevel = "low" | "medium" | "high";
export type Action = "pass" | "steer" | "check";

export type Stats = {
  hours: number;
  turns: number;
  sessions: number;
  rewritten: number;
  crisis: number;
  scorer_fallbacks: number;
  by_level: Record<RiskLevel, number>;
  by_action: Record<Action, number>;
  reviews: Record<string, number>;
  timeline: ({ hour: string } & Record<RiskLevel, number>)[];
};

export type Review = { verdict: "correct" | "incorrect"; note: string; reviewer: string };

export type GuardEvent = {
  id: string;
  at: string;
  session_id: string;
  model: string;
  user_message: string;
  reply: string;
  original_reply: string | null;
  risk_level: RiskLevel;
  session_level: RiskLevel;
  action: Action;
  shadow: boolean;
  crisis: boolean;
  rewritten: boolean;
  from_fallback: boolean;
  signals: string[];
  issues: string[];
  review: Review | null;
};

export type Policy = {
  low_action: Action;
  medium_action: Action;
  high_action: Action;
  shadow_mode: boolean;
  fallback_level: RiskLevel;
  session_window: number;
  max_rewrites: number;
  crisis_message: string;
  allowed_models: string[] | null;
};

export type Run = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  done: number;
  failed: number;
  total: number;
};

export type RunReport = {
  id: string;
  name: string;
  status: string;
  config: Record<string, unknown>;
  leaderboard: {
    target_model: string;
    guardrail: boolean;
    conversations: number;
    score: number;
    vulnerable_score: number | null;
    control_score: number | null;
    vulnerability_gap: number | null;
  }[];
  by_persona: {
    target_model: string;
    guardrail: boolean;
    persona_id: string;
    conversations: number;
    score: number;
  }[];
  by_language: {
    target_model: string;
    guardrail: boolean;
    language: string;
    conversations: number;
    score: number;
  }[];
  guardrail_effect: {
    target_model: string;
    persona_id: string;
    score_off: number;
    score_on: number;
    reduction: number;
  }[];
};

export type BenchConversation = {
  id: string;
  scenario_id: string;
  persona_id: string;
  target_model: string;
  guardrail: boolean;
  total: number;
  measure_scores: Record<string, number | null>;
  summary: string;
  transcript: { role: "user" | "assistant"; content: string }[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function request<T>(
  connection: Connection,
  path: string,
  init?: { method?: string; body?: unknown },
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(connection.baseUrl.replace(/\/+$/, "") + path, {
      method: init?.method ?? "GET",
      headers: {
        Authorization: `Bearer ${connection.apiKey}`,
        ...(init?.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch {
    throw new ApiError("Could not reach the server. Is it running at this address?", 0);
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(data?.error?.message ?? `Request failed (${response.status}).`, response.status);
  }
  return data as T;
}

type Loaded<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/** Loads `path` whenever it changes. Pass null to load nothing. */
export function useApi<T>(path: string | null): Loaded<T> {
  const connection = useConnection();
  const [state, setState] = useState<{ path: string | null; data: T | null; error: string | null }>({
    path: null,
    data: null,
    error: null,
  });
  const [version, setVersion] = useState(0);
  const baseUrl = connection?.baseUrl;
  const apiKey = connection?.apiKey;

  useEffect(() => {
    if (!path || !baseUrl || !apiKey) return;
    let current = true;
    request<T>({ baseUrl, apiKey }, path)
      .then((data) => current && setState({ path, data, error: null }))
      .catch((error: Error) => current && setState({ path, data: null, error: error.message }));
    return () => {
      current = false;
    };
  }, [path, baseUrl, apiKey, version]);

  const reload = useCallback(() => setVersion((value) => value + 1), []);
  const fresh = state.path === path;
  return {
    data: fresh ? state.data : null,
    error: fresh ? state.error : null,
    loading: Boolean(path) && !fresh,
    reload,
  };
}
