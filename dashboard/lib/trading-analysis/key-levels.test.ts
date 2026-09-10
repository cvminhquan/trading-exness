import { describe, expect, it } from "vitest";
import type { MultiTimeframeAnalysis } from "@/domain";
import { buildKeyLevelsSnapshot } from "@/lib/trading-analysis/key-levels";

const _baseTf = (partial: Record<string, unknown>) =>
  ({
    timeframe: "M15",
    status: "OK",
    candleTimestamp: null,
    signal: "NEUTRAL",
    confidence: 0,
    ema20: null,
    ema50: null,
    ema200: null,
    rsi14: null,
    atr14: 10,
    macdLine: null,
    macdSignal: null,
    macdHist: null,
    structureClassification: "RANGE",
    sequence: [],
    nearestSupport: null,
    nearestResistance: null,
    volume: { current: null, average: null, ratio: null, spike: false },
    pattern: { name: null, direction: null },
    score: {
      trendScore: 0,
      structureScore: 0,
      momentumScore: 0,
      locationScore: 0,
      volumeScore: 0,
      totalScore: 0,
    },
    ...partial,
  }) as unknown as MultiTimeframeAnalysis["timeframes"][string];

describe("buildKeyLevelsSnapshot", () => {
  it("picks nearest support below and resistance above without inventing prices", () => {
    const analysis = {
      symbol: "XAUUSD",
      keySupports: [4340, 4348, 4300],
      keyResistances: [4378, 4390, 4420],
      currentPrice: 4360.61,
      timeframes: {
        M15: _baseTf({ timeframe: "M15", nearestSupport: 4348, nearestResistance: 4378 }),
        H1: _baseTf({
          timeframe: "H1",
          nearestSupport: 4348,
          nearestResistance: 4378,
          atr14: 12,
        }),
        H4: _baseTf({ timeframe: "H4" }),
        D1: _baseTf({ timeframe: "D1" }),
      },
    } as unknown as MultiTimeframeAnalysis;

    const snap = buildKeyLevelsSnapshot(analysis, 4360.61);
    expect(snap.support).not.toBeNull();
    expect(snap.resistance).not.toBeNull();
    expect(snap.support!.high).toBeLessThan(4360.61);
    expect(snap.resistance!.low).toBeGreaterThan(4360.61);
    expect(snap.priceBetween).toBe(true);
    expect(snap.support!.timeframe).toBe("H1");
  });

  it("returns null sides when no valid levels around price", () => {
    const analysis = {
      symbol: "XAUUSD",
      keySupports: [],
      keyResistances: [],
      currentPrice: 100,
      timeframes: {
        M15: _baseTf({ timeframe: "M15" }),
        H1: _baseTf({ timeframe: "H1" }),
        H4: _baseTf({ timeframe: "H4" }),
        D1: _baseTf({ timeframe: "D1" }),
      },
    } as unknown as MultiTimeframeAnalysis;

    const snap = buildKeyLevelsSnapshot(analysis, 100);
    expect(snap.support).toBeNull();
    expect(snap.resistance).toBeNull();
  });
});
