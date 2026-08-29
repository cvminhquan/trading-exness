"use client";

import { useMemo, useState } from "react";
import type { BacktestReport } from "@/domain";
import { isBacktestMetricsAvailable } from "@/lib/constants/backtest";
import { downsampleForChart } from "@/lib/backtest/derive";
import { toBacktestRunSummary } from "@/lib/backtest/summary";
import { BacktestConfigCard } from "@/components/backtest/BacktestConfigCard";
import { BacktestDatasetCard } from "@/components/backtest/BacktestDatasetCard";
import { BacktestDrawdownSection } from "@/components/backtest/BacktestDrawdownSection";
import { BacktestHeader } from "@/components/backtest/BacktestHeader";
import { BacktestInsufficientData } from "@/components/backtest/BacktestInsufficientData";
import { BacktestInterpretation } from "@/components/backtest/BacktestInterpretation";
import { BacktestRunSelector } from "@/components/backtest/BacktestRunSelector";
import { DataQualityCard } from "@/components/backtest/DataQualityCard";
import { ExecutionAssumptions } from "@/components/backtest/ExecutionAssumptions";
import { MonthlyPerformanceSection } from "@/components/backtest/MonthlyPerformanceSection";
import { PerformanceMetrics } from "@/components/backtest/PerformanceMetrics";
import { PnlBreakdown } from "@/components/backtest/PnlBreakdown";
import { RDistribution } from "@/components/backtest/RDistribution";
import { TradeDistribution } from "@/components/backtest/TradeDistribution";
import { TradeStatistics } from "@/components/backtest/TradeStatistics";
import { EquityChart } from "@/components/shared/EquityChart";

type BacktestAnalyticsViewProps = {
  reports: BacktestReport[];
};

export const BacktestAnalyticsView = ({ reports }: BacktestAnalyticsViewProps) => {
  const [selectedId, setSelectedId] = useState(reports[0]?.id ?? null);
  const report = reports.find((r) => r.id === selectedId) ?? reports[0];
  const summaries = useMemo(() => reports.map(toBacktestRunSummary), [reports]);

  const metricsAvailable = report
    ? isBacktestMetricsAvailable({
        status: report.status,
        isMeaningful: report.dataset?.isMeaningful ?? false,
        totalCandles: report.dataset?.totalCandles ?? 0,
      })
    : false;

  const chartEquity = useMemo(
    () => (report ? downsampleForChart(report.equityCurve) : []),
    [report],
  );
  const chartDrawdown = useMemo(
    () => (report ? downsampleForChart(report.drawdownCurve) : []),
    [report],
  );

  if (!report) return null;

  return (
    <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
      <BacktestRunSelector
        runs={summaries}
        selectedId={report.id}
        onSelect={setSelectedId}
      />
      <div className="min-w-0 space-y-6">
        <BacktestHeader report={report} />

        {!metricsAvailable ? (
          <>
            <BacktestInsufficientData report={report} />
            {report.dataset ? (
              <BacktestDatasetCard
                dataset={report.dataset}
                symbol={report.symbol}
                timeframe={report.timeframe}
              />
            ) : null}
            {report.execution ? (
              <BacktestConfigCard execution={report.execution} strategy={report.strategy} />
            ) : null}
            {report.assumptions ? <ExecutionAssumptions assumptions={report.assumptions} /> : null}
            {report.dataset ? <DataQualityCard dataset={report.dataset} /> : null}
            <BacktestInterpretation classification={report.classification} />
          </>
        ) : (
          <>
            {report.dataset ? (
              <BacktestDatasetCard
                dataset={report.dataset}
                symbol={report.symbol}
                timeframe={report.timeframe}
              />
            ) : null}
            {report.execution ? (
              <BacktestConfigCard execution={report.execution} strategy={report.strategy} />
            ) : null}
            {report.performance ? <PerformanceMetrics performance={report.performance} /> : null}
            {report.performance ? <PnlBreakdown performance={report.performance} /> : null}
            <EquityChart
              data={chartEquity}
              title="Đường cong vốn"
              variant="backtest"
              initialBalance={report.performance?.initialBalance}
            />
            <BacktestDrawdownSection
              drawdownCurve={chartDrawdown}
              performance={report.performance}
            />
            {report.performance ? <TradeStatistics performance={report.performance} /> : null}
            <RDistribution rAnalysis={report.rAnalysis} />
            <TradeDistribution trades={report.trades} />
            <MonthlyPerformanceSection data={report.monthlyPerformance} />
            {report.assumptions ? <ExecutionAssumptions assumptions={report.assumptions} /> : null}
            {report.dataset ? <DataQualityCard dataset={report.dataset} /> : null}
            <BacktestInterpretation classification={report.classification} />
          </>
        )}
      </div>
    </div>
  );
};
