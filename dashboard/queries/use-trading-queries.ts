"use client";

import { useQuery } from "@tanstack/react-query";
import { tradingRepository } from "@/repositories";
import { tradingKeys } from "./keys";

export const useBotStatus = () =>
  useQuery({
    queryKey: tradingKeys.botStatus(),
    queryFn: () => tradingRepository.getBotStatus(),
  });

export const useAccountSnapshot = () =>
  useQuery({
    queryKey: tradingKeys.account(),
    queryFn: () => tradingRepository.getAccountSnapshot(),
  });

export const useDashboardOverview = () =>
  useQuery({
    queryKey: tradingKeys.overview(),
    queryFn: () => tradingRepository.getDashboardOverview(),
  });

export const usePositions = () =>
  useQuery({
    queryKey: tradingKeys.positions(),
    queryFn: () => tradingRepository.getPositions(),
  });

export const useTrades = () =>
  useQuery({
    queryKey: tradingKeys.trades(),
    queryFn: () => tradingRepository.getTrades(),
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

export const useSessionContext = () =>
  useQuery({
    queryKey: tradingKeys.session(),
    queryFn: () => tradingRepository.getSessionContext(),
  });
