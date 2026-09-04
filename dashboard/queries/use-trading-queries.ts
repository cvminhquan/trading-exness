"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AccountProfileId } from "@/domain";
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

export const useSessionContext = () =>
  useQuery({
    queryKey: tradingKeys.session(),
    queryFn: () => tradingRepository.getSessionContext(),
    refetchInterval: 5_000,
  });

export const useQuotes = () =>
  useQuery({
    queryKey: tradingKeys.quotes(),
    queryFn: () => tradingRepository.getQuotes(),
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

export const useTrades = () =>
  useQuery({
    queryKey: tradingKeys.trades(),
    queryFn: () => tradingRepository.getTrades(),
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
