import type { TradingRepository } from "./trading-repository";
import {
  accountSnapshotSchema,
  accountSwitchStateSchema,
  backtestReportSchema,
  dashboardOverviewSchema,
  positionSchema,
  quoteSchema,
  riskSnapshotSchema,
  sessionContextSchema,
  strategySnapshotSchema,
  systemSettingsSchema,
  tradeSchema,
  paperTradingSchema,
} from "@/domain/schemas";
import { buildBacktestQueryString, buildTradeQueryString } from "@/domain/api/params";
import type { ApiClient } from "@/lib/api/client";
import { API_V1 } from "@/lib/api/paths";
import { ApiError } from "@/lib/api/errors";

export class ApiTradingRepository implements TradingRepository {
  constructor(private readonly client: ApiClient) {}

  async getBotStatus() {
    const session = await this.getSessionContext();
    return session.botStatus;
  }

  getAccountSnapshot() {
    return this.client.get(API_V1.account, accountSnapshotSchema);
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

  getQuotes() {
    return this.client.get(API_V1.quotes, quoteSchema.array());
  }

  getPaperTrading() {
    return this.client.get(API_V1.paper, paperTradingSchema);
  }
}
