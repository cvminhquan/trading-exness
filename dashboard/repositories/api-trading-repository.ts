import type { TradingRepository } from "./trading-repository";
import {
  accountOverviewSchema,
  accountSnapshotSchema,
  accountSwitchStateSchema,
  backtestReportSchema,
  dailyRealizedPnlSchema,
  dashboardOverviewSchema,
  positionSchema,
  quoteSchema,
  riskSnapshotSchema,
  sessionContextSchema,
  strategySnapshotSchema,
  systemSettingsSchema,
  tradeSchema,
  paperTradingSchema,
  tradeAnalysisSchema,
  multiTimeframeAnalysisSchema,
  executionCandidateStatusSchema,
  marketSynthesisSchema,
} from "@/domain/schemas";
import { buildBacktestQueryString, buildTradeQueryString } from "@/domain/api/params";
import type { ApiClient } from "@/lib/api/client";
import { API_V1 } from "@/lib/api/paths";
import { ApiError } from "@/lib/api/errors";
import type { MarketSynthesisQuery } from "./trading-repository";

export class ApiTradingRepository implements TradingRepository {
  constructor(private readonly client: ApiClient) {}

  async getBotStatus() {
    const session = await this.getSessionContext();
    return session.botStatus;
  }

  getAccountSnapshot() {
    return this.client.get(API_V1.account, accountSnapshotSchema);
  }

  getAccountOverview() {
    return this.client.get(API_V1.accountOverview, accountOverviewSchema);
  }

  getDailyRealizedPnl(days = 7) {
    return this.client.get(API_V1.accountPnlDaily, dailyRealizedPnlSchema.array(), {
      query: `?days=${days}`,
    });
  }

  getDashboardOverview() {
    return this.client.get(API_V1.overview, dashboardOverviewSchema);
  }

  getPositions() {
    return this.client.getList(API_V1.positions, positionSchema);
  }

  getTrades(params?: Parameters<TradingRepository["getTrades"]>[0]) {
    return this.client.getList(API_V1.trades, tradeSchema, {
      query: buildTradeQueryString(params),
    });
  }

  getStrategySnapshot() {
    return this.client.get(API_V1.strategy, strategySnapshotSchema);
  }

  getRiskSnapshot() {
    return this.client.get(API_V1.risk, riskSnapshotSchema);
  }

  getBacktestReports(params?: Parameters<TradingRepository["getBacktestReports"]>[0]) {
    return this.client.getList(API_V1.backtests, backtestReportSchema, {
      query: buildBacktestQueryString(params),
    });
  }

  async getBacktestReport(id: string) {
    try {
      return await this.client.get(API_V1.backtest(id), backtestReportSchema);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  }

  getSystemSettings() {
    return this.client.get(API_V1.settings, systemSettingsSchema);
  }

  getAccountSwitchState() {
    return this.client.get(API_V1.accounts, accountSwitchStateSchema);
  }

  setActiveAccount(profile: Parameters<TradingRepository["setActiveAccount"]>[0]) {
    return this.client.post(API_V1.activeAccount, accountSwitchStateSchema, { profile });
  }

  getSessionContext() {
    return this.client.get(API_V1.status, sessionContextSchema);
  }

  getQuotes(symbols?: string[]) {
    const query =
      symbols && symbols.length > 0
        ? `?symbols=${encodeURIComponent(symbols.join(","))}`
        : "";
    return this.client.get(API_V1.quotes, quoteSchema.array(), { query });
  }

  getPaperTrading() {
    return this.client.get(API_V1.paper, paperTradingSchema);
  }

  getTradeAnalysis(symbol = "XAUUSD") {
    return this.client.get(API_V1.analysisSymbol(symbol), tradeAnalysisSchema);
  }

  getMultiTimeframeAnalysis(symbol = "XAUUSD") {
    return this.client.get(
      API_V1.multiTimeframeAnalysis(symbol),
      multiTimeframeAnalysisSchema,
    );
  }

  getExecutionCandidateStatus(symbol = "XAUUSD") {
    return this.client.get(
      API_V1.executionCandidate(symbol),
      executionCandidateStatusSchema,
    );
  }

  getMarketSynthesis(symbol = "XAUUSD", query: MarketSynthesisQuery = {}) {
    const params = new URLSearchParams();
    if (query.forceRefresh) {
      params.set("forceRefresh", "true");
    }
    const qs = params.toString();
    return this.client.get(API_V1.marketSynthesis(symbol), marketSynthesisSchema, {
      query: qs ? `?${qs}` : "",
    });
  }
}
