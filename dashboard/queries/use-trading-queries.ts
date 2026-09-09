"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AccountProfileId } from "@/domain";
import type { TradeListParams } from "@/domain/api/params";
import { tradingRepository } from "@/repositories";
import { tradingKeys } from "./keys";

export const useBotStatus = () =>
  useQuery({
    queryKey: tradingKeys.botStatus(),
    queryFn: () => tradingRepository.getBotStatus(),
    refetchInterval: 5_000,
  });

export const useAccountSnapshot = () =>
  useQuery({
    queryKey: tradingKeys.account(),
    queryFn: () => tradingRepository.getAccountSnapshot(),
    refetchInterval: 5_000,
  });

export const useAccountOverview = () =>
  useQuery({
    queryKey: tradingKeys.accountOverview(),
    queryFn: () => tradingRepository.getAccountOverview(),
    refetchInterval: 3_000,
  });

export const useDailyRealizedPnl = (days = 7) =>
  useQuery({
    queryKey: tradingKeys.accountPnlDaily(days),
    queryFn: () => tradingRepository.getDailyRealizedPnl(days),
    refetchInterval: 60_000,
  });

export const useTradeAnalysis = (symbol = "XAUUSD") =>
  useQuery({
    queryKey: tradingKeys.analysis(symbol),
    queryFn: () => tradingRepository.getTradeAnalysis(symbol),
    refetchInterval: 5_000,
  });

export const useMultiTimeframeAnalysis = (symbol = "XAUUSD") =>
  useQuery({
    queryKey: tradingKeys.mtfAnalysis(symbol),
    queryFn: () => tradingRepository.getMultiTimeframeAnalysis(symbol),
    refetchInterval: 5_000,
  });

/** finalSignal cho mọi symbol dashboard — dùng SymbolTabs hiển thị LONG/SHORT/WAIT. */
export const useDashboardSymbolSignals = (symbols: readonly string[]) => {
  const queries = useQueries({
    queries: symbols.map((symbol) => ({
      queryKey: tradingKeys.mtfAnalysis(symbol),
      queryFn: () => tradingRepository.getMultiTimeframeAnalysis(symbol),
      refetchInterval: 5_000,
      staleTime: 4_000,
    })),
  });

  const signals: Record<string, "LONG" | "SHORT" | "WAIT" | undefined> = {};
  symbols.forEach((symbol, index) => {
    signals[symbol] = queries[index]?.data?.finalSignal;
  });

  return signals;
};

export const useExecutionCandidateStatus = (symbol = "XAUUSD") =>
  useQuery({
    queryKey: tradingKeys.executionCandidate(symbol),
    queryFn: () => tradingRepository.getExecutionCandidateStatus(symbol),
    refetchInterval: 5_000,
  });

/** Phase 16.3.4 — không forceRefresh khi poll thường (nhận cache backend). */
export const useMarketSynthesis = (symbol: string) =>
  useQuery({
    queryKey: tradingKeys.marketSynthesis(symbol),
    queryFn: () => tradingRepository.getMarketSynthesis(symbol),
    enabled: Boolean(symbol),
    staleTime: 45_000,
    refetchInterval: 60_000,
  });

export const useSessionContext = () =>
  useQuery({
    queryKey: tradingKeys.session(),
    queryFn: () => tradingRepository.getSessionContext(),
    refetchInterval: 5_000,
  });

export const useQuotes = (symbols?: string[]) =>
  useQuery({
    queryKey:
      symbols && symbols.length > 0
        ? tradingKeys.quotesFor(symbols)
        : tradingKeys.quotes(),
    queryFn: () => tradingRepository.getQuotes(symbols),
    refetchInterval: 2_000,
    staleTime: 1_000,
  });

export const usePaperTrading = () =>
  useQuery({
    queryKey: tradingKeys.paper(),
    queryFn: () => tradingRepository.getPaperTrading(),
    refetchInterval: 5_000,
  });

export const useDashboardOverview = () =>
  useQuery({
    queryKey: tradingKeys.overview(),
    queryFn: () => tradingRepository.getDashboardOverview(),
    refetchInterval: 5_000,
  });

export const usePositions = () =>
  useQuery({
    queryKey: tradingKeys.positions(),
    queryFn: () => tradingRepository.getPositions(),
    refetchInterval: 3_000,
  });

export const useTrades = (params?: TradeListParams) =>
  useQuery({
    queryKey: tradingKeys.trades(params),
    queryFn: () =>
      tradingRepository.getTrades({
        page: 1,
        pageSize: 200,
        ...params,
      }),
    refetchInterval: 15_000,
  });

export const useStrategySnapshot = () =>
  useQuery({
    queryKey: tradingKeys.strategy(),
    queryFn: () => tradingRepository.getStrategySnapshot(),
  });

export const useRiskSnapshot = () =>
  useQuery({
    queryKey: tradingKeys.risk(),
    queryFn: () => tradingRepository.getRiskSnapshot(),
  });

export const useBacktestReports = () =>
  useQuery({
    queryKey: tradingKeys.backtests(),
    queryFn: () => tradingRepository.getBacktestReports(),
  });

export const useBacktestReport = (id: string | null) =>
  useQuery({
    queryKey: tradingKeys.backtest(id ?? "none"),
    queryFn: () => {
      if (!id) return Promise.resolve(null);
      return tradingRepository.getBacktestReport(id);
    },
    enabled: Boolean(id),
  });

export const useSystemSettings = () =>
  useQuery({
    queryKey: tradingKeys.settings(),
    queryFn: () => tradingRepository.getSystemSettings(),
  });

export const useAccountSwitchState = () =>
  useQuery({
    queryKey: tradingKeys.accounts(),
    queryFn: () => tradingRepository.getAccountSwitchState(),
    refetchInterval: 5_000,
  });

export const useSetActiveAccount = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profile: AccountProfileId) => tradingRepository.setActiveAccount(profile),
    onSuccess: async (data) => {
      queryClient.setQueryData(tradingKeys.accounts(), data);
      await queryClient.invalidateQueries({ queryKey: tradingKeys.all });
    },
  });
};

export const useClosePosition = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; confirm: string }) =>
      tradingRepository.closePosition(input.id, { confirm: input.confirm }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: tradingKeys.all });
    },
  });
};

export const useClosePositions = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      confirm: string;
      positionIds?: string[];
      closeAll?: boolean;
    }) => tradingRepository.closePositions(input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: tradingKeys.all });
    },
  });
};

/** Phase 16.3.5 — analysis-only chat (not a broker mutation). */
export const useMarketAnalystChat = (symbol: string) =>
  useMutation({
    mutationFn: (input: { message: string; sessionId?: string | null }) =>
      tradingRepository.postAnalystChat(symbol, input),
  });
