import { describe, expect, it } from "vitest";
import { summarise } from "@/lib/results";

const sample = {
  metrics: {
    target_fpr: 0.05,
    models: { "fused (w=0.4)": { test_dev: { detection_rate: 0.9, false_alarm_rate: 0.04 } } },
    efficiency: { analyse_ms_p50: 36.7, peak_rss_mb: 705 },
  },
  heldout_v2: { models: { fused: { detection_rate: 0.43, false_alarm_rate: 0.043, auc_roc: 0.855 } } },
  campaign: {
    n_products: 200,
    attacks: [
      { attack: "genuine", caught_as_expected: 1 },
      { attack: "inpaint", caught_as_expected: 1 },
      { attack: "replay", caught_as_expected: 0.97 },
    ],
  },
};

describe("summarise", () => {
  it("reads the headline figures from the result files", () => {
    const h = summarise(sample)!;
    expect(h.seenDetection).toBe(0.9);
    expect(h.heldoutV2Detection).toBe(0.43);
    expect(h.products).toBe(200);
    expect(h.analyseMs).toBe(36.7);
  });
  it("does not count the genuine control as an attack, and only counts fully caught attacks", () => {
    const h = summarise(sample)!;
    expect(h.attackTypes).toBe(2);
    expect(h.attackTypesCaught).toBe(1);
  });
  it("returns NaN, never an invented number, when a file is missing", () => {
    const h = summarise({ metrics: { models: {} } })!;
    expect(Number.isNaN(h.heldoutV2Detection)).toBe(true);
    expect(Number.isNaN(h.products)).toBe(true);
  });
  it("returns null without metrics", () => {
    expect(summarise({})).toBeNull();
  });
});
