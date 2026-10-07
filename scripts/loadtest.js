// Load test for the guardrail proxy, run with k6 (https://k6.io):
//
//   k6 run -e BASE_URL=http://localhost:8000 -e API_KEY=<key> -e MODEL=<model> scripts/loadtest.js
//
// It sends a mix of calm and risky messages and reports how long replies take.
// Point MirrorGuard at a fast stand-in model to measure MirrorGuard's own overhead,
// or at a real model to measure the whole path.

import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API_KEY = __ENV.API_KEY;
const MODEL = __ENV.MODEL || "groq/openai/gpt-oss-20b";

const byAction = { pass: new Trend("reply_ms_pass", true), steer: new Trend("reply_ms_steer", true) };

export const options = {
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 20),
      duration: __ENV.DURATION || "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
  },
};

const MESSAGES = [
  "Should I learn Python or Go first?",
  "What is a good way to plan my week?",
  "Can you explain what an index fund is?",
  "I have not slept for 3 days and I am quitting my job tomorrow. Genius, right?",
];

export default function () {
  const text = MESSAGES[Math.floor(Math.random() * MESSAGES.length)];
  const response = http.post(
    `${BASE_URL}/v1/chat/completions`,
    JSON.stringify({ model: MODEL, messages: [{ role: "user", content: text }] }),
    {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${API_KEY}`,
        "X-Session-Id": `load-${__VU}-${__ITER}`,
      },
    },
  );
  const ok = check(response, {
    "status is 200": (r) => r.status === 200,
    "has a reply": (r) => r.status === 200 && r.json("choices.0.message.content").length > 0,
  });
  if (ok) {
    const trend = byAction[response.json("mirrorguard.action")];
    if (trend) trend.add(response.timings.duration);
  }
}
