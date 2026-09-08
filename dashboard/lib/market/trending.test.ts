import { describe, expect, it } from "vitest";
import { formatCompactMarketPrice, formatSignedPercentChange } from "@/lib/format";
import { computeSessionChangePct, quoteMidPrice } from "@/lib/market/quote-price";
import { mergeWatchSymbols, normalizeSymbol, TRENDING_SYMBOLS } from "@/lib/market/trending";
import type { Quote } from "@/domain";

describe("trending symbols", () => {
  it("keeps exactly 5 default trending symbols", () => {
    expect(TRENDING_SYMBOLS).toHaveLength(5);
  });

  it("normalizes and merges extras without duplicates", () => {
    expect(normalizeSymbol(" gbp/usd ")).toBe("GBPUSD");
    expect(mergeWatchSymbols(["BTCUSD", "GBPUSD"])).toEqual([
      ...TRENDING_SYMBOLS,
      "GBPUSD",
    ]);
  });
});

describe("quote mid + session change", () => {
  const quote: Quote = {
    symbol: "XAUUSD",
    bid: 100,
    ask: 102,
    last: null,
    spread: 2,
    digits: 2,
    available: true,
    updatedAt: "2026-09-07T12:00:00.000Z",
    freshness: "LIVE",
  };

  it("uses mid from bid/ask", () => {
    expect(quoteMidPrice(quote)).toBe(101);
  });

  it("computes session change percent", () => {
    expect(computeSessionChangePct(101, 100)).toBeCloseTo(1);
    expect(computeSessionChangePct(99, 100)).toBeCloseTo(-1);
    expect(computeSessionChangePct(100, null)).toBeNull();
  });
});

describe("compact price formatting", () => {
  it("formats millions and signed percent", () => {
    expect(formatCompactMarketPrice(108450)).toMatch(/108/);
    expect(formatSignedPercentChange(5.73)).toBe("+5.73%");
    expect(formatSignedPercentChange(-0.84)).toBe("-0.84%");
  });
});
