import { describe, expect, it } from "vitest";
import { aggregateQuoteFreshness } from "@/lib/market/freshness";
import type { Quote } from "@/domain";

const quote = (freshness: Quote["freshness"], available = true): Quote => ({
  symbol: "XAUUSD",
  bid: available ? 2350.1 : null,
  ask: available ? 2350.3 : null,
  last: available ? 2350.2 : null,
  spread: available ? 0.2 : null,
  digits: 2,
  available,
  updatedAt: "2026-08-29T10:00:00.000Z",
  freshness,
});

describe("aggregateQuoteFreshness", () => {
  it("trả UNAVAILABLE khi không có quote", () => {
    expect(aggregateQuoteFreshness([])).toBe("UNAVAILABLE");
  });

  it("ưu tiên freshness của XAUUSD vì đó là symbol V1", () => {
    expect(
      aggregateQuoteFreshness([
        quote("STALE"),
        { ...quote("LIVE"), symbol: "BTCUSD" },
      ]),
    ).toBe("STALE");
  });

  it("không gọi LIVE khi chỉ còn STALE", () => {
    expect(aggregateQuoteFreshness([quote("STALE"), quote("UNAVAILABLE", false)])).toBe("STALE");
  });

  it("UNAVAILABLE khi không có tick khả dụng", () => {
    expect(aggregateQuoteFreshness([quote("UNAVAILABLE", false)])).toBe("UNAVAILABLE");
  });
});
