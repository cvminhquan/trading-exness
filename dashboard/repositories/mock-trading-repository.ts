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
  mockMarketSynthesis,
  mockAnalystChatResponse,
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
  private openPositions = [...mockPositions];

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
    return [...this.openPositions];
  }

  async closePosition(id: string, body: { confirm: string }) {
    await simulateDelay(80);
    if (body.confirm !== "CLOSE" && body.confirm !== "LIVE-CLOSE") {
      throw new Error("Cần nhập đúng cụm xác nhận để đóng vị thế.");
    }
    const target = this.openPositions.find((p) => p.id === id);
    if (!target) {
      throw new Error("Không tìm thấy vị thế.");
    }
    this.openPositions = this.openPositions.filter((p) => p.id !== id);
    return {
      requested: 1,
      closed: 1,
      failed: 0,
      accountProfile: this.activeProfile,
      results: [
        {
          positionId: id,
          symbol: target.symbol,
          success: true,
          dryRun: false,
          executionPrice: target.currentPrice,
          volume: target.volume,
          errorMessage: null,
        },
      ],
    };
  }

  async closePositions(body: {
    confirm: string;
    positionIds?: string[];
    closeAll?: boolean;
  }) {
    await simulateDelay(100);
    if (body.confirm !== "CLOSE-ALL" && body.confirm !== "LIVE-CLOSE-ALL") {
      throw new Error("Cần nhập đúng cụm xác nhận để đóng vị thế.");
    }
    const ids = body.closeAll
      ? this.openPositions.map((p) => p.id)
      : (body.positionIds ?? []);
    const closing = this.openPositions.filter((p) => ids.includes(p.id));
    this.openPositions = this.openPositions.filter((p) => !ids.includes(p.id));
    return {
      requested: closing.length,
      closed: closing.length,
      failed: 0,
      accountProfile: this.activeProfile,
      results: closing.map((p) => ({
        positionId: p.id,
        symbol: p.symbol,
        success: true,
        dryRun: false,
        executionPrice: p.currentPrice,
        volume: p.volume,
        errorMessage: null,
      })),
    };
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

  async getMarketSynthesis() {
    await simulateDelay(100);
    return mockMarketSynthesis;
  }

  async postAnalystChat(symbol: string, body: { message: string; sessionId?: string | null }) {
    await simulateDelay(120);
    return mockAnalystChatResponse(symbol, body.message, body.sessionId);
  }
}
