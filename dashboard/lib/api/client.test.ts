import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { tradingKeys } from "@/queries/keys";
import { MockTradingRepository } from "@/repositories/mock-trading-repository";
import { ApiTradingRepository } from "@/repositories/api-trading-repository";
import type { TradingRepository } from "@/repositories/trading-repository";
import {
  createTradingRepository,
  resetTradingRepository,
} from "@/repositories/create-trading-repository";

const itemSchema = z.object({ id: z.string(), value: z.number() });

describe("ApiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses a valid data envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ data: { id: "a", value: 1 } }), { status: 200 }),
      ),
    );

    const client = createApiClient({ apiBaseUrl: "http://test", apiTimeoutMs: 5000 });
    const result = await client.get("/items", itemSchema);
    expect(result).toEqual({ id: "a", value: 1 });
  });

  it("rejects invalid response with VALIDATION_FAILED", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ data: { id: 1, value: "bad" } }), { status: 200 }),
      ),
    );

    const client = createApiClient({ apiBaseUrl: "http://test", apiTimeoutMs: 5000 });
    await expect(client.get("/items", itemSchema)).rejects.toMatchObject({
      code: "VALIDATION_FAILED",
      message: "Dữ liệu phản hồi không hợp lệ.",
    });
  });

  it("normalizes API error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "BOT_NOT_CONNECTED", message: "Bot hiện chưa kết nối." },
          }),
          { status: 503 },
        ),
      ),
    );

    const client = createApiClient({ apiBaseUrl: "http://test", apiTimeoutMs: 5000 });
    await expect(client.get("/status", itemSchema)).rejects.toMatchObject({
      code: "BOT_NOT_CONNECTED",
      status: 503,
    });
  });
});

describe("tradingKeys", () => {
  it("includes filters in trades key", () => {
    expect(tradingKeys.trades({ symbol: "XAUUSD", page: 2 })).toEqual([
      "trading",
      "trades",
      { symbol: "XAUUSD", page: 2 },
    ]);
  });

  it("nests backtest id under backtests", () => {
    expect(tradingKeys.backtest("run-1")).toEqual([
      "trading",
      "backtests",
      {},
      "run-1",
    ]);
  });
});

describe("repository interface compatibility", () => {
  const assertRepositoryShape = (repo: TradingRepository) => {
    expect(typeof repo.getBotStatus).toBe("function");
    expect(typeof repo.getAccountSnapshot).toBe("function");
    expect(typeof repo.getDashboardOverview).toBe("function");
    expect(typeof repo.getPositions).toBe("function");
    expect(typeof repo.getTrades).toBe("function");
    expect(typeof repo.getStrategySnapshot).toBe("function");
    expect(typeof repo.getRiskSnapshot).toBe("function");
    expect(typeof repo.getBacktestReports).toBe("function");
    expect(typeof repo.getBacktestReport).toBe("function");
    expect(typeof repo.getSystemSettings).toBe("function");
    expect(typeof repo.getAccountSwitchState).toBe("function");
    expect(typeof repo.setActiveAccount).toBe("function");
    expect(typeof repo.getSessionContext).toBe("function");
  };

  it("MockTradingRepository implements TradingRepository", () => {
    assertRepositoryShape(new MockTradingRepository());
  });

  it("ApiTradingRepository implements TradingRepository", () => {
    const client = createApiClient({ apiBaseUrl: "http://test", apiTimeoutMs: 1000 });
    assertRepositoryShape(new ApiTradingRepository(client));
  });
});

describe("createTradingRepository", () => {
  beforeEach(() => {
    resetTradingRepository();
    vi.unstubAllEnvs();
  });

  it("returns mock repository by default", () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "mock");
    const repo = createTradingRepository();
    expect(repo).toBeInstanceOf(MockTradingRepository);
  });

  it("returns api repository when configured", () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "api");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");
    const repo = createTradingRepository();
    expect(repo).toBeInstanceOf(ApiTradingRepository);
  });
});
