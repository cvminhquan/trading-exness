import type { TradingRepository } from "./trading-repository";
import type { AccountProfileId, AccountSwitchState, SessionContext } from "@/domain";
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
  mockQuotes,
  simulateDelay,
} from "@/mocks/data";
import { mockBacktestReports } from "@/mocks/backtest-data";

const MOCK_NOTE =
  "Chuyển tài khoản chỉ đổi phiên đăng nhập MT5 để xem dữ liệu. Bot không được phép đặt lệnh live.";

const buildMockAccountState = (active: AccountProfileId): AccountSwitchState => ({
  activeProfile: active,
  tradingMode: "DEMO",
  allowLiveTrading: false,
  readOnly: true,
  liveOrdersEnabled: false,
  note: MOCK_NOTE,
  profiles: [
    {
      id: "demo",
      kind: "demo",
      label: "Tài khoản demo",
      configured: true,
      login: 12345678,
      server: "Exness-MT5Trial",
      active: active === "demo",
    },
    {
      id: "live",
      kind: "live",
      label: "Tài khoản thật",
      configured: true,
      login: 999000111,
      server: "Exness-MT5Real",
      active: active === "live",
    },
  ],
});

export class MockTradingRepository implements TradingRepository {
  private activeProfile: AccountProfileId = "demo";

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

  async getAccountSwitchState() {
    await simulateDelay(80);
    return buildMockAccountState(this.activeProfile);
  }

  async setActiveAccount(profile: AccountProfileId) {
    await simulateDelay(120);
    this.activeProfile = profile;
    return buildMockAccountState(this.activeProfile);
  }

  async getSessionContext(): Promise<SessionContext> {
    await simulateDelay(150);
    if (this.activeProfile === "live") {
      return {
        ...mockSession,
        accountProfile: "live",
        accountLabel: "Exness-MT5Real #999000111",
      };
    }
    return { ...mockSession, accountProfile: "demo" };
  }

  async getQuotes() {
    await simulateDelay(80);
    return mockQuotes;
  }
}
