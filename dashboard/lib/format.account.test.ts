import { describe, expect, it } from "vitest";
import {
  formatCurrency,
  formatSignedCurrency,
  getPnLSentiment,
} from "@/lib/format";
import { accountOverviewSchema } from "@/domain/schemas";

describe("PnL formatting (Phase 15)", () => {
  it("formats positive PnL with +", () => {
    expect(formatSignedCurrency(0.13)).toBe("+$0.13");
    expect(getPnLSentiment(0.13)).toBe("profit");
  });

  it("formats negative PnL with -", () => {
    expect(formatSignedCurrency(-0.08)).toBe("-$0.08");
    expect(getPnLSentiment(-0.08)).toBe("loss");
  });

  it("formats zero without sign", () => {
    expect(formatSignedCurrency(0)).toBe("$0.00");
    expect(getPnLSentiment(0)).toBe("flat");
  });

  it("formats tiny account values with 2 decimals", () => {
    expect(formatCurrency(10.5)).toBe("$10.50");
    expect(formatCurrency(10.63)).toBe("$10.63");
  });
});

describe("accountOverviewSchema", () => {
  it("parses LIVE overview", () => {
    const parsed = accountOverviewSchema.parse({
      status: "LIVE",
      balance: 10.5,
      equity: 10.63,
      margin: 1.24,
      freeMargin: 9.39,
      marginLevel: 857.25,
      currency: "USD",
      unrealizedPnl: 0.13,
      realizedPnlToday: -0.08,
      totalPnlToday: 0.05,
      dailyReturnPct: 0.47,
      dailyReturnAvailable: true,
      openPositionsCount: 1,
      server: "Exness-MT5Trial17",
      tradeMode: "demo",
      loginMasked: "***4158",
      updatedAt: "2026-09-07T12:00:00.000Z",
      ageSeconds: 2,
      message: null,
      safety: {
        tradeMode: "DEMO",
        server: "Exness-MT5Trial17",
        mt5Status: "CONNECTED",
        algoTrading: "ENABLED",
        killSwitch: "ON",
        executionMode: "PAPER",
      },
    });
    expect(parsed.dailyReturnAvailable).toBe(true);
  });

  it("parses disconnected overview with null metrics", () => {
    const parsed = accountOverviewSchema.parse({
      status: "DISCONNECTED",
      updatedAt: "2026-09-07T12:00:00.000Z",
      ageSeconds: 32,
      message: "Mất kết nối MT5.",
      safety: {
        tradeMode: "DEMO",
        server: null,
        mt5Status: "DISCONNECTED",
        algoTrading: "UNKNOWN",
        killSwitch: "ON",
        executionMode: "PAPER",
      },
    });
    expect(parsed.balance).toBeUndefined();
    expect(parsed.dailyReturnAvailable).toBe(false);
  });

  it("allows N/A daily return", () => {
    const parsed = accountOverviewSchema.parse({
      status: "STALE",
      balance: 10.5,
      equity: 10.5,
      unrealizedPnl: 0,
      realizedPnlToday: 0,
      totalPnlToday: 0,
      dailyReturnPct: null,
      dailyReturnAvailable: false,
      openPositionsCount: 0,
      updatedAt: "2026-09-07T12:00:00.000Z",
      ageSeconds: 20,
      safety: {
        tradeMode: "DEMO",
        server: "Exness-MT5Trial17",
        mt5Status: "CONNECTED",
        algoTrading: "DISABLED",
        killSwitch: "ON",
        executionMode: "PAPER",
      },
    });
    expect(parsed.dailyReturnPct).toBeNull();
  });
});
