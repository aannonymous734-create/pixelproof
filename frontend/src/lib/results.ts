import { useEffect, useState } from "react";
import { API_BASE } from "./api";

/** The few headline figures the Overview shows. Every field is read from results/*.json (via the API). */
export interface Headline {
  targetFpr: number;
  seenDetection: number;
  seenFalseAlarm: number;
  heldoutV2Detection: number;
  heldoutV2FalseAlarm: number;
  heldoutV2Auc: number;
  products: number;
  attackTypes: number; // attack scenarios, excluding the genuine control
  attackTypesCaught: number; // of those, how many were caught with the expected status on every product
  analyseMs: number;
  peakMb: number;
}

const fusedOf = (models: Record<string, any> | undefined) => {
  const k = Object.keys(models ?? {}).find((x) => x.toLowerCase().includes("fused"));
  return k ? models![k] : undefined;
};

/** Pure function so it can be unit-tested; missing data yields NaN, never an invented number. */
export function summarise(r: any): Headline | null {
  if (!r?.metrics) return null;
  const seen = fusedOf(r.metrics.models)?.test_dev;
  const v2 = fusedOf(r.heldout_v2?.models);
  const attacks: any[] = (r.campaign?.attacks ?? []).filter((a: any) => a.attack !== "genuine");
  return {
    targetFpr: r.metrics.target_fpr ?? NaN,
    seenDetection: seen?.detection_rate ?? NaN,
    seenFalseAlarm: seen?.false_alarm_rate ?? NaN,
    heldoutV2Detection: v2?.detection_rate ?? NaN,
    heldoutV2FalseAlarm: v2?.false_alarm_rate ?? NaN,
    heldoutV2Auc: v2?.auc_roc ?? NaN,
    products: r.campaign?.n_products ?? NaN,
    attackTypes: attacks.length,
    attackTypesCaught: attacks.filter((a) => a.caught_as_expected === 1).length,
    analyseMs: r.metrics.efficiency?.analyse_ms_p50 ?? NaN,
    peakMb: r.metrics.efficiency?.peak_rss_mb ?? NaN,
  };
}

export type ResultsState = { status: "loading" } | { status: "error" } | { status: "ok"; data: Headline };

export function useHeadline(): ResultsState {
  const [state, setState] = useState<ResultsState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/api/v1/results`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j) => {
        const data = summarise(j);
        if (alive) setState(data ? { status: "ok", data } : { status: "error" });
      })
      .catch(() => alive && setState({ status: "error" }));
    return () => {
      alive = false;
    };
  }, []);
  return state;
}
