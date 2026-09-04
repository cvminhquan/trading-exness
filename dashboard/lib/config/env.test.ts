import { afterEach, describe, expect, it, vi } from "vitest";
import { getDashboardEnv, resolveApiBaseUrl } from "@/lib/config/env";
import { createTradingRepository, resetTradingRepository } from "@/repositories/create-trading-repository";
import { ApiTradingRepository } from "@/repositories/api-trading-repository";
import { MockTradingRepository } from "@/repositories/mock-trading-repository";

describe("resolveApiBaseUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("đổi localhost thành 127.0.0.1 khi chạy trên server", () => {
    expect(resolveApiBaseUrl("http://localhost:8000/")).toBe("http://127.0.0.1:8000");
  });

  it("dùng API nội bộ khi env là path rewrite", () => {
    vi.stubEnv("API_INTERNAL_URL", "http://127.0.0.1:8000");
    expect(resolveApiBaseUrl("/engine")).toBe("http://127.0.0.1:8000");
  });

  it("giữ path tương đối khi có window", () => {
    vi.stubGlobal("window", { document: {} });
    expect(resolveApiBaseUrl("/engine")).toBe("/engine");
  });
});

describe("getDashboardEnv dataSource", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    resetTradingRepository();
  });

  it("dùng API khi NEXT_PUBLIC_DATA_SOURCE=api — không fallback mock", () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "api");
    expect(getDashboardEnv().dataSource).toBe("api");
    resetTradingRepository();
    expect(createTradingRepository()).toBeInstanceOf(ApiTradingRepository);
  });

  it("dùng mock khi NEXT_PUBLIC_DATA_SOURCE=mock", () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "mock");
    expect(getDashboardEnv().dataSource).toBe("mock");
    resetTradingRepository();
    expect(createTradingRepository()).toBeInstanceOf(MockTradingRepository);
  });
});
