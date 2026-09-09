import type {
  AccountSnapshot,
  AccountOverview,
  AccountProfileId,
  AccountSwitchState,
  BacktestReport,
  BotStatus,
  DailyRealizedPnl,
  DashboardOverview,
  Position,
  RiskSnapshot,
  SessionContext,
  StrategySnapshot,
  SystemSettings,
  Trade,
  Quote,
  PaperTrading,
  TradeAnalysis,
  MultiTimeframeAnalysis,
  ExecutionCandidateStatus,
  MarketSynthesis,
} from "@/domain";
import type { BacktestListParams, TradeListParams } from "@/domain/api/params";

export type MarketSynthesisQuery = {
  forceRefresh?: boolean;
};

export interface TradingRepository {
  getBotStatus(): Promise<BotStatus>;
  getAccountSnapshot(): Promise<AccountSnapshot>;
  getAccountOverview(): Promise<AccountOverview>;
  getDailyRealizedPnl(days?: number): Promise<DailyRealizedPnl[]>;
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
  getQuotes(symbols?: string[]): Promise<Quote[]>;
  getPaperTrading(): Promise<PaperTrading>;
  getTradeAnalysis(symbol?: string): Promise<TradeAnalysis>;
  getMultiTimeframeAnalysis(symbol?: string): Promise<MultiTimeframeAnalysis>;
  getExecutionCandidateStatus(symbol?: string): Promise<ExecutionCandidateStatus>;
  getMarketSynthesis(
    symbol?: string,
    query?: MarketSynthesisQuery,
  ): Promise<MarketSynthesis>;
}
