import type { TradingRepository } from "./trading-repository";
import type { AccountProfileId, AccountSwitchState, SessionContext } from "@/domain";
import {
  mockAccount,
  mockAccountOverview,
  mockBotStatus,
  mockDailyRealizedPnl,
  mockDashboardOverview,
  mockPositions,
  mockRisk,
  mockSession,
  mockSettings,
  mockStrategy,
  mockTrades,
  mockQuotes,
  mockPaperTrading,
  mockTradeAnalysis,
  mockMultiTimeframeAnalysis,
  mockExecutionCandidateStatus,
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

  async getAccountOverview() {
    await simulateDelay();
    return mockAccountOverview;
  }

  async getDailyRealizedPnl(days = 7) {
    await simulateDelay();
    return mockDailyRealizedPnl.slice(-days);
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

  async getQuotes(symbols?: string[]) {
    await simulateDelay(80);
    if (!symbols?.length) return mockQuotes;
    const wanted = new Set(symbols.map((s) => s.toUpperCase()));
    const found = mockQuotes.filter((q) => wanted.has(q.symbol));
    const missing = symbols
      .map((s) => s.toUpperCase())
      .filter((s) => !found.some((q) => q.symbol === s))
      .map((symbol) => ({
        symbol,
        bid: null,
        ask: null,
        last: null,
        spread: null,
        digits: 5,
        available: false,
        updatedAt: new Date().toISOString(),
        freshness: "UNAVAILABLE" as const,
      }));
    return [...found, ...missing];
  }

  async getPaperTrading() {
    await simulateDelay(80);
    return mockPaperTrading;
  }

  async getTradeAnalysis() {
    await simulateDelay(80);
    return mockTradeAnalysis;
  }

  async getMultiTimeframeAnalysis() {
    await simulateDelay(80);
    return mockMultiTimeframeAnalysis;
  }

  async getExecutionCandidateStatus() {
    await simulateDelay(80);
    return mockExecutionCandidateStatus;
  }
}
