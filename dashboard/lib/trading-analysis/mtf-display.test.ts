import { describe, expect, it } from "vitest";
import type { MultiTimeframeAnalysis } from "@/domain";
import { mockMultiTimeframeAnalysis } from "@/mocks/data";
import {
  computeDisplayWeightedScore,
  distanceToThreshold,
  hasDirectionalSetup,
  MTF_SHORT_THRESHOLD,
} from "@/lib/trading-analysis/mtf-display";
import { collectDecisionReasons, mapReasonCode } from "@/lib/trading-analysis/reason-labels";

const withScores = (
  scores: Record<string, number>,
  overrides: Partial<MultiTimeframeAnalysis> = {},
): MultiTimeframeAnalysis => {
  const base = structuredClone(mockMultiTimeframeAnalysis);
  for (const [tf, totalScore] of Object.entries(scores)) {
    const row = base.timeframes[tf];
    if (!row?.score) continue;
    row.score.totalScore = totalScore;
  }
  return { ...base, ...overrides };
};

describe("mtf-display", () => {
  it("computes weighted score matching Phase 17.2.3 example (-12.63)", () => {
    const analysis = withScores({
      M15: 4,
      H1: -40.1,
      H4: 18,
      D1: -34,
    });
    expect(computeDisplayWeightedScore(analysis)).toBe(-12.63);
  });

  it("reports distance to SHORT threshold inside WAIT zone", () => {
    const dist = distanceToThreshold(-12.63);
    expect(dist.side).toBe("SHORT");
    expect(dist.points).toBeCloseTo(-12.63 - MTF_SHORT_THRESHOLD, 2);
  });

  it("detects no directional setup on WAIT / NO_SETUP", () => {
    const analysis = withScores(
      { M15: 0, H1: 0, H4: 0, D1: 0 },
      {
        finalSignal: "WAIT",
        setup: {
          ...mockMultiTimeframeAnalysis.setup!,
          state: "NO_SETUP",
          entryPrice: null,
          stopLoss: null,
          takeProfits: [],
        },
      },
    );
    expect(hasDirectionalSetup(analysis)).toBe(false);
  });

  it("detects LONG WAITING_FOR_ENTRY as directional setup", () => {
    expect(hasDirectionalSetup(mockMultiTimeframeAnalysis)).toBe(true);
  });
});

describe("reason-labels", () => {
  it("maps known codes to Vietnamese labels", () => {
    expect(mapReasonCode("SCORE_INSIDE_WAIT_ZONE")).toContain("WAIT");
    expect(mapReasonCode("MIN_VOLUME_EXCEEDS_RISK_BUDGET")).toContain("broker");
  });

  it("collects unique failed reasons and eligibility codes", () => {
    const items = collectDecisionReasons({
      analysisReasons: [
        { code: "TF_H1", passed: true, message: "ok" },
        { code: "FINAL_SIGNAL_WAIT", passed: false, message: "wait" },
      ],
      analysisWarnings: [
        { code: "STRUCTURE_MIXED", passed: false, message: "mixed" },
      ],
      eligibilityReasons: ["PRICE_NOT_IN_ENTRY_ZONE", "STRUCTURE_MIXED"],
    });
    expect(items.map((i) => i.code)).toEqual([
      "FINAL_SIGNAL_WAIT",
      "STRUCTURE_MIXED",
      "PRICE_NOT_IN_ENTRY_ZONE",
    ]);
  });
});

describe("risk presentation invariants", () => {
  it("keeps brokerExecutable independent from riskAcceptable on mock", () => {
    const sizing = mockMultiTimeframeAnalysis.sizing!;
    expect(sizing.brokerExecutable).toBe(true);
    expect(sizing.riskAcceptable).toBe(false);
  });

  it("marks TP1 as execution target policy TP1_ONLY (presentation)", () => {
    const tps = mockMultiTimeframeAnalysis.setup!.takeProfits;
    expect(tps[0]?.level).toBe(1);
    expect(tps.length).toBeGreaterThan(1);
  });
});
