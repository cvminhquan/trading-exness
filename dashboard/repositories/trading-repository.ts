import type {
  AccountSnapshot,
  AccountProfileId,
  AccountSwitchState,
  BacktestReport,
  BotStatus,
  DashboardOverview,
  Position,
  RiskSnapshot,
  SessionContext,
  StrategySnapshot,
  SystemSettings,
  Trade,
  Quote,
} from "@/domain";
import type { BacktestListParams, TradeListParams } from "@/domain/api/params";

export interface TradingRepository {
  getBotStatus(): Promise<BotStatus>;
  getAccountSnapshot(): Promise<AccountSnapshot>;
  getDashboardOverview(): Promise<DashboardOverview>;
  getPositions(): Promise<Position[]>;
  getTrades(params?: TradeListParams): Promise<Trade[]>;
  getStrategySnapshot(): Promise<StrategySnapshot>;
  getRiskSnapshot(): Promise<RiskSnapshot>;
  getBacktestReports(params?: BacktestListParams): Promise<BacktestReport[]>;
  getBacktestReport(id: string): Promise<BacktestReport | null>;
  getSystemSettings(): Promise<SystemSettings>;
  getAccountSwitchState(): Promise<AccountSwitchState>;
  setActiveAccount(profile: AccountProfileId): Promise<AccountSwitchState>;
  getSessionContext(): Promise<SessionContext>;
  getQuotes(): Promise<Quote[]>;
}
