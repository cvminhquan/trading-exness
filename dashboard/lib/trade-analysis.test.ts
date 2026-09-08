import { describe, expect, it } from "vitest";
import { tradeAnalysisSchema } from "@/domain/schemas";
import { mockTradeAnalysis } from "@/mocks/data";

describe("tradeAnalysisSchema", () => {
  it("parses BUY + BLOCKED small-account mock", () => {
    const parsed = tradeAnalysisSchema.parse(mockTradeAnalysis);
    expect(parsed.signal).toBe("BUY");
    expect(parsed.executionStatus).toBe("BLOCKED");
    expect(parsed.sizing?.equity).toBe(10.5);
    expect(parsed.sizing?.brokerExecutable).toBe(true);
    expect(parsed.sizing?.riskAcceptable).toBe(false);
    expect(parsed.blockingReasons[0]?.code).toBe("MIN_VOLUME_EXCEEDS_RISK_BUDGET");
    expect(parsed.reasons.every((r) => typeof r.passed === "boolean")).toBe(true);
  });

  it("parses WAIT without trade plan", () => {
    const parsed = tradeAnalysisSchema.parse({
      ...mockTradeAnalysis,
      signal: "WAIT",
      executionStatus: "NOT_APPLICABLE",
      trade: null,
      sizing: null,
      blockingReasons: [],
      reasons: [
        {
          code: "REGIME",
          passed: false,
          message: "Market regime is NEUTRAL",
        },
      ],
    });
    expect(parsed.signal).toBe("WAIT");
    expect(parsed.trade).toBeNull();
  });

  it("parses SELL", () => {
    const parsed = tradeAnalysisSchema.parse({
      ...mockTradeAnalysis,
      signal: "SELL",
      regime: "BEARISH",
      executionStatus: "READY",
      blockingReasons: [],
      sizing: {
        ...mockTradeAnalysis.sizing!,
        riskAcceptable: true,
        estimatedRiskUsd: 0.04,
        estimatedRiskPct: 0.4,
      },
    });
    expect(parsed.signal).toBe("SELL");
    expect(parsed.executionStatus).toBe("READY");
  });

  it("parses Phase 16.1 structure fields", () => {
    const parsed = tradeAnalysisSchema.parse(mockTradeAnalysis);
    expect(parsed.strategySignal).toBe("BUY");
    expect(parsed.contextAssessment).toBe("BLOCKED");
    expect(parsed.structure?.classification).toBe("BULLISH");
    expect(parsed.structure?.sequence).toEqual(["HH", "HL", "HH"]);
  });
});
