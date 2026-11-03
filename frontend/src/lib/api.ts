// Thin client for the FastAPI ground station. The base URL is configurable so the same build runs
// from the ground VM, a dev proxy, or the host. Nothing is mocked: every value shown comes from here.

const STORED = (() => {
  try {
    return localStorage.getItem("pxp_api_base") || "";
  } catch {
    return "";
  }
})();
// Default: same origin (FastAPI serves this app), so it works offline inside the VM.
export let API_BASE = STORED || "";

export function setApiBase(url: string) {
  API_BASE = url.replace(/\/$/, "");
  try {
    localStorage.setItem("pxp_api_base", API_BASE);
  } catch {
    /* ignore */
  }
}

export type Verdict =
  | "VERIFIED"
  | "SIGNED_BUT_SUSPICIOUS"
  | "ALTERED_AFTER_CAPTURE"
  | "SUSPICIOUS"
  | "UNVERIFIED_NO_TRACES";

export interface Analysis {
  verdict: Verdict;
  action: string;
  integrity: { status: string; ok: boolean };
  reasons: string[];
  content: {
    manipulated: boolean;
    type: string;
    manipulation_score: number;
    threshold: number;
    reencoding_probability?: number;
    probabilities: Record<string, number>;
    evidence: string[];
    model: string;
    tiles?: number;
    input_note?: string;
  };
  pixel_digest: string;
  product_id?: string | null;
  capture_time?: string | null;
  heatmap_png_b64?: string;
  ledger_hash?: string;
}

export type Severity = "critical" | "warning" | "info";

export interface LedgerEntry {
  time: string;
  hash: string;
  channel: string;
  product_id: string | null;
  verdict: string;
  action: string;
  integrity: string;
  content_type: string;
  score: number;
  severity: Severity;
}

export interface Stats {
  total: number;
  verified: number;
  unverified_no_traces: number;
  suspicious: number;
  rejected: number;
  invalid_signatures: number;
  replays: number;
  manipulation_alerts: number;
  released: number;
  quarantined: number;
  audit_chain_valid: boolean;
}

export interface Identity {
  key_id: string;
  role: string;
  owner: string;
  revoked: boolean;
  fingerprint_sha256: string;
  public_key: string;
}

export interface Station {
  server_time: string;
  identities: Identity[];
  downlinks_received: number;
  last_downlink: { time: string; product_id: string; verdict: string; integrity: string; action: string } | null;
  audit_chain_valid: boolean;
  replay_memory: { products: number; sources: number };
  trust_policy: { hash: string; signature: string; pinned: boolean; max_future_minutes: number; replay_protection: string };
  detector: { version: string | null; mode: string; model_sha256: string; model_card_match: boolean | null };
  lab_mode: boolean;
}

export interface LabScenario {
  name: string;
  id: string;
  kind: "integrity" | "replay" | "content" | "compromised_source";
  title: string;
  attacker_action: string;
  why_it_fails: string;
  expected: string;
}

export interface LabTrial {
  trial: number;
  sample: string;
  product_id: string;
  matches_expected: boolean;
  integrity_status: string;
  verdict: string;
  action: string;
  signed_digest?: string;
  received_digest?: string;
  first_delivery?: string;
  control_status?: string;
  reasons: string[];
  content: { flagged: boolean; type: string | null; score: number | null; threshold: number | null; evidence: string[] };
  ledger_hash: string | null;
  timeline: { t_ms: number; actor: "satellite" | "attacker" | "ground"; event: string; [k: string]: unknown }[];
}

export interface LabResult extends LabScenario {
  scenario: string;
  n: number;
  matches_expected: number;
  rate: number;
  control: { n: number; verified?: number; false_alarms?: number };
  audit_log: { entries: number; chain_valid: boolean };
  trials: LabTrial[];
  environment: { python: string; platform: string; cpu_threads: number | null; model_mode: string; seed: number };
  duration_s: number;
}

export interface LabRunSummary {
  time: string;
  scenario: string;
  id: string;
  title: string;
  expected: string;
  n: number;
  matches_expected: number;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, init);
  if (!r.ok) {
    // FastAPI errors look like {"detail": "..."}: show the sentence, not the JSON
    const raw = await r.text().catch(() => "");
    let detail = raw;
    try {
      const j = JSON.parse(raw);
      detail = typeof j.detail === "string" ? j.detail : raw;
    } catch {
      /* not JSON: keep the raw text */
    }
    throw new Error(`${r.status} ${r.statusText}${detail ? `: ${detail}` : ""}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<Record<string, unknown>>("/api/v1/health"),
  registry: () => req<Record<string, any>>("/api/v1/registry"),
  ledger: (limit = 100) =>
    req<{ chain_valid: boolean; first_bad_entry: number | null; entries: LedgerEntry[] }>(
      `/api/v1/ledger?limit=${limit}`,
    ),
  stats: () => req<Stats>("/api/v1/stats"),
  station: () => req<Station>("/api/v1/station"),
  labScenarios: () => req<{ enabled: boolean; max_trials: number; scenarios: LabScenario[] }>("/api/v1/lab/scenarios"),
  labRuns: () => req<LabRunSummary[]>("/api/v1/lab/runs"),
  labRun: (scenario: string, n: number) =>
    req<LabResult>("/api/v1/lab/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario, n }),
    }),
  analyse: (image: File, manifest?: File) => {
    const fd = new FormData();
    fd.append("image", image);
    if (manifest) fd.append("manifest", manifest);
    return req<Analysis>("/api/v1/analyse", { method: "POST", body: fd });
  },
};

export const VERDICT_TONE: Record<Verdict, "ok" | "warn" | "bad" | "info" | "mute"> = {
  VERIFIED: "ok",
  SIGNED_BUT_SUSPICIOUS: "warn",
  ALTERED_AFTER_CAPTURE: "bad",
  SUSPICIOUS: "warn",
  UNVERIFIED_NO_TRACES: "mute",
};
