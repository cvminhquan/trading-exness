import type { TradingRepository } from "./trading-repository";
import {
  mockAccount,
  mockBotStatus,
  mockDashboardOverview,
  mockPositions,
  mockRisk,
  mockSession,
  mockSettings,
  mockStrategy,
  mockTrades,
  simulateDelay,
} from "@/mocks/data";
import { mockBacktestReports } from "@/mocks/backtest-data";

export class MockTradingRepository implements TradingRepository {
  async getBotStatus() {
    await simulateDelay();
    return mockBotStatus;
  }

  async getAccountSnapshot() {
    await simulateDelay();
    return mockAccount;
  }

  async getDashboardOverview() {
    await simulateDelay();
    return mockDashboardOverview;
  }

  async getPositions() {
    await simulateDelay();
    return mockPositions;
  }

  async getTrades() {
    await simulateDelay();
    return mockTrades;
  }

  async getStrategySnapshot() {
    await simulateDelay();
    return mockStrategy;
  }

  async getRiskSnapshot() {
    await simulateDelay();
    return mockRisk;
  }

  async getBacktestReports() {
    await simulateDelay();
    return mockBacktestReports;
  }

  async getBacktestReport(id: string) {
    await simulateDelay();
    return mockBacktestReports.find((r) => r.id === id) ?? null;
  }

  async getSystemSettings() {
    await simulateDelay();
    return mockSettings;
  }

  async getSessionContext() {
    await simulateDelay(150);
    return mockSession;
  }
}