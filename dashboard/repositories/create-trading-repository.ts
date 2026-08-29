import { getDashboardEnv } from "@/lib/config/env";
import { createApiClient } from "@/lib/api/client";
import { ApiTradingRepository } from "./api-trading-repository";
import { MockTradingRepository } from "./mock-trading-repository";
import type { TradingRepository } from "./trading-repository";

export const createTradingRepository = (): TradingRepository => {
  const env = getDashboardEnv();
  if (env.dataSource === "api") {
    const client = createApiClient({
      apiBaseUrl: env.apiBaseUrl,
      apiTimeoutMs: env.apiTimeoutMs,
    });
    return new ApiTradingRepository(client);
  }
  return new MockTradingRepository();
};

let repositoryInstance: TradingRepository | null = null;

export const getTradingRepository = (): TradingRepository => {
  if (!repositoryInstance) {
    repositoryInstance = createTradingRepository();
  }
  return repositoryInstance;
};

/** Chỉ dùng trong test — reset singleton. */
export const resetTradingRepository = (): void => {
  repositoryInstance = null;
};

/** Chỉ dùng trong test — inject implementation. */
export const setTradingRepository = (repository: TradingRepository): void => {
  repositoryInstance = repository;
};
