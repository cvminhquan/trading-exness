/** Mirrors trading-engine dataset_inspection.py thresholds. */
export const BACKTEST_DATASET = {
  minMeaningfulCandles: 5_000,
  recommendedCandles: 20_000,
} as const;

export type BacktestQualityStatus = "VALID" | "WARNING" | "INSUFFICIENT";

export const getDatasetQualityStatus = (
  totalCandles: number,
  isMeaningful: boolean,
): BacktestQualityStatus => {
  if (!isMeaningful || totalCandles < BACKTEST_DATASET.minMeaningfulCandles) {
    return "INSUFFICIENT";
  }
  if (totalCandles < BACKTEST_DATASET.recommendedCandles) {
    return "WARNING";
  }
  return "VALID";
};

export const isBacktestMetricsAvailable = (params: {
  status: string;
  isMeaningful: boolean;
  totalCandles: number;
}): boolean =>
  params.status === "completed" &&
  params.isMeaningful &&
  params.totalCandles >= BACKTEST_DATASET.minMeaningfulCandles;
