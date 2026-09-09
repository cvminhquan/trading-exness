"use client";

import { useCallback, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { QueryState } from "@/components/shared/States";
import { Skeleton } from "@/components/shared/Skeletons";
import type { MarketSynthesis } from "@/domain";
import { MARKET_CONTEXT as L } from "@/lib/i18n/vi";
import {
  alignmentLabel,
  alignmentTone,
  biasLabel,
  biasTone,
  directionForGoldLabel,
  evidenceLabel,
  eventRiskLabel,
  eventRiskTone,
  safeExternalHref,
  stateLabel,
  statusBadgeVariant,
  statusLabel,
  timeframeRoleLabel,
  toneClasses,
  type SemanticTone,
} from "@/lib/market-context/display";
import { formatRelativeAgo } from "@/lib/trading-analysis/mtf-display";
import { cn } from "@/lib/utils";
import { tradingKeys } from "@/queries/keys";
import { useMarketSynthesis } from "@/queries/use-trading-queries";
import { tradingRepository } from "@/repositories";

type MarketContextSectionProps = {
  symbol: string;
};

const MarketContextSkeleton = () => (
  <div className="surface-card space-y-4 px-5 py-4" aria-hidden>
    <Skeleton className="h-5 w-48" />
    <div className="grid gap-3 md:grid-cols-3">
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
    <Skeleton className="h-28 w-full" />
  </div>
);

const TonePill = ({
  tone,
  children,
}: {
  tone: SemanticTone;
  children: ReactNode;
}) => (
  <span
    className={cn(
      "inline-flex items-center rounded-full border px-2.5 py-1 text-[12px] font-semibold",
      toneClasses(tone),
    )}
  >
    {children}
  </span>
);

const textToneClass = (tone: SemanticTone): string => {
  switch (tone) {
    case "positive":
      return "text-[var(--positive)]";
    case "negative":
      return "text-[var(--negative)]";
    case "warning":
      return "text-[var(--warning)]";
    case "info":
      return "text-[var(--accent)]";
    default:
      return "text-[var(--foreground-secondary)]";
  }
};

const TechnicalExternalComparison = ({ data }: { data: MarketSynthesis }) => {
  const tech = data.technicalView;
  const ext = data.externalView;
  const tfs = tech.timeframes ?? {};

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--muted)]">
            {L.technical}
          </p>
          <p className="mt-1 text-[13px] text-[var(--foreground-secondary)]">
            {timeframeRoleLabel("M15").label}
          </p>
          <div className="mt-2">
            <TonePill tone={biasTone(tech.primaryBias)}>
              {biasLabel(tech.primaryBias)}
            </TonePill>
          </div>
          <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-[var(--muted)]">
            {L.botSignal}
          </p>
          <p
            className="mt-1 text-[15px] font-semibold text-[var(--foreground)]"
            aria-label={`${L.botSignal}: ${tech.botSignal}`}
          >
            {tech.botSignal}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--muted)]">
            {L.external}
          </p>
          <div className="mt-2">
            <TonePill tone={biasTone(ext.externalBias)}>
              {biasLabel(ext.externalBias)}
            </TonePill>
          </div>
          <p className="mt-3 text-[12px] text-[var(--foreground-secondary)]">
            {evidenceLabel(ext.evidenceStrength)} · {ext.sourceCount} nguồn
          </p>
        </div>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--muted)]">
            {L.relation}
          </p>
          <div className="mt-2">
            <TonePill tone={alignmentTone(ext.alignmentWithTechnical)}>
              {alignmentLabel(ext.alignmentWithTechnical)}
            </TonePill>
          </div>
          <p className="mt-3 text-[12px] text-[var(--foreground-secondary)]">
            {L.synthesisState}: {stateLabel(data.synthesis.state)}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {(["M15", "H1", "H4", "D1"] as const).map((tf) => {
          const row = tfs[tf];
          const trend = String(row?.trend ?? "UNKNOWN").toUpperCase();
          const meta = timeframeRoleLabel(tf);
          return (
            <div
              key={tf}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] px-2.5 py-1.5 text-[12px]"
            >
              <span className="font-semibold text-[var(--foreground)]">
                {meta.label}
              </span>
              <span className="mx-1.5 text-[var(--muted)]">·</span>
              <span className={cn("font-medium", textToneClass(biasTone(trend)))}>
                {biasLabel(trend)}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-[var(--muted)]">
        M15 là khung PRIMARY — H4/D1 không ghi đè tín hiệu M15 trên bối cảnh này.
      </p>
    </div>
  );
};

const DriversPanel = ({ data }: { data: MarketSynthesis }) => {
  const drivers = data.externalView.topDrivers;
  if (drivers.length === 0) {
    return (
      <p className="text-[13px] text-[var(--muted)]">{L.noDrivers}</p>
    );
  }
  return (
    <ul className="space-y-2">
      {drivers.map((d) => (
        <li
          key={`${d.driver}-${d.directionForGold}`}
          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[13px] font-semibold text-[var(--foreground)]">
              {d.driver.replaceAll("_", " ")}
            </span>
            <TonePill tone={biasTone(d.directionForGold)}>
              {directionForGoldLabel(d.directionForGold)}
            </TonePill>
          </div>
          {d.summary ? (
            <p className="mt-1 text-[12px] text-[var(--foreground-secondary)]">
              {d.summary}
            </p>
          ) : null}
          <p className="mt-1 text-[11px] text-[var(--muted)]">
            {evidenceLabel(d.evidenceStrength)}
            {d.sourceIds.length > 0
              ? ` · ${d.sourceIds.length} nguồn`
              : ""}
          </p>
        </li>
      ))}
    </ul>
  );
};

const EventRiskPanel = ({ data }: { data: MarketSynthesis }) => {
  const risk = data.externalView.eventRisk;
  const events = data.externalView.importantEvents;
  return (
    <div className="space-y-3">
      <div
        className={cn(
          "rounded-xl border px-3 py-2",
          toneClasses(eventRiskTone(risk)),
        )}
        role="status"
        aria-label={`${L.eventRisk}: ${eventRiskLabel(risk)}`}
      >
        <p className="text-[11px] font-semibold uppercase tracking-wide opacity-80">
          {L.eventRisk}
        </p>
        <p className="text-[16px] font-semibold">{eventRiskLabel(risk)}</p>
      </div>
      {events.length === 0 ? (
        <p className="text-[13px] text-[var(--muted)]">{L.noEvents}</p>
      ) : (
        <ul className="space-y-2">
          {events.map((e) => (
            <li
              key={`${e.eventName}-${e.status}`}
              className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2"
            >
              <p className="text-[13px] font-semibold text-[var(--foreground)]">
                {e.eventName}
              </p>
              <p className="mt-0.5 text-[12px] text-[var(--foreground-secondary)]">
                {e.status} · {eventRiskLabel(e.importance)}
                {e.scheduledAt ? ` · ${e.scheduledAt}` : ""}
              </p>
              {e.note ? (
                <p className="mt-1 text-[11px] text-[var(--muted)]">{e.note}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const AiSynthesisPanel = ({ data }: { data: MarketSynthesis }) => {
  const [open, setOpen] = useState(false);
  const syn = data.synthesis;
  const ai = data.aiMetadata;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[14px] font-semibold text-[var(--foreground)]">
          {L.aiTitle}
        </h3>
        {!ai.used ? (
          <Badge variant="default">
            {ai.fallbackUsed ? L.fallbackLabel : L.deterministicLabel}
          </Badge>
        ) : null}
      </div>
      <p className="text-[12px] text-[var(--muted)]">{L.aiSubtitle}</p>
      <p className="text-[13px] leading-relaxed text-[var(--foreground)]">
        {syn.summary}
      </p>
      <button
        type="button"
        className="text-[13px] font-semibold text-[var(--accent)] hover:text-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Thu gọn chi tiết" : L.details}
      </button>
      {open ? (
        <div className="space-y-2 rounded-xl border border-[var(--border)] bg-[var(--surface-subtle)] p-3 text-[12px] text-[var(--foreground-secondary)]">
          <p>
            <span className="font-semibold text-[var(--foreground)]">
              Kỹ thuật:{" "}
            </span>
            {syn.technicalExplanation}
          </p>
          <p>
            <span className="font-semibold text-[var(--foreground)]">
              Bên ngoài:{" "}
            </span>
            {syn.externalExplanation}
          </p>
          <p>
            <span className="font-semibold text-[var(--foreground)]">
              Quan hệ:{" "}
            </span>
            {syn.alignmentExplanation}
          </p>
          <p>
            <span className="font-semibold text-[var(--foreground)]">
              Rủi ro:{" "}
            </span>
            {syn.riskExplanation}
          </p>
        </div>
      ) : null}
    </div>
  );
};

const SourcesPanel = ({ data }: { data: MarketSynthesis }) => {
  if (data.sources.length === 0) {
    return <p className="text-[13px] text-[var(--muted)]">{L.noSources}</p>;
  }
  return (
    <ol className="space-y-2">
      {data.sources.map((s, index) => {
        const href = safeExternalHref(s.url);
        return (
          <li
            key={s.sourceId || `${s.domain}-${index}`}
            className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[12px]"
          >
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-semibold text-[var(--muted)]">
                [{index + 1}]
              </span>
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                >
                  {s.title || s.domain || s.sourceId}
                </a>
              ) : (
                <span className="font-semibold text-[var(--foreground)]">
                  {s.title || s.domain || s.sourceId}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-[var(--foreground-secondary)]">
              {s.domain}
              {s.freshness ? ` · ${s.freshness}` : ""}
              {s.publishedAt ? ` · ${s.publishedAt}` : " · chưa có thời gian xuất bản"}
            </p>
          </li>
        );
      })}
    </ol>
  );
};

const MarketContextBody = ({
  data,
  onRefresh,
  refreshing,
}: {
  data: MarketSynthesis;
  onRefresh: () => void;
  refreshing: boolean;
}) => {
  const extStatus = data.externalView.status;
  const showExternalHint =
    data.status === "TECHNICAL_ONLY" ||
    extStatus === "DISABLED" ||
    extStatus === "UNAVAILABLE";

  return (
    <section
      className="surface-card space-y-4 px-5 py-4"
      aria-label={L.title}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[16px] font-semibold text-[var(--foreground)]">
              {L.title}
            </h2>
            <Badge variant={statusBadgeVariant(data.status)}>
              {statusLabel(data.status)}
            </Badge>
            <span className="text-[12px] font-medium text-[var(--foreground-secondary)]">
              {data.symbol}
            </span>
          </div>
          <p className="mt-1 text-[12px] text-[var(--muted)]">{L.subtitle}</p>
          <p className="mt-1 text-[11px] text-[var(--muted)]">
            {L.updated} {formatRelativeAgo(data.generatedAt)} · {L.readOnlyNote}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-[13px] font-semibold text-[var(--accent)] transition-colors hover:border-[var(--accent-muted)] hover:bg-[var(--accent-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-60"
          aria-label={L.refresh}
        >
          {refreshing ? L.refreshing : L.refresh}
        </button>
      </div>

      {showExternalHint ? (
        <p
          className="rounded-xl border border-[var(--border)] bg-[var(--surface-subtle)] px-3 py-2 text-[13px] text-[var(--foreground-secondary)]"
          role="status"
        >
          {extStatus === "DISABLED"
            ? L.externalDisabled
            : L.externalUnavailable}
        </p>
      ) : null}

      <TechnicalExternalComparison data={data} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-[14px] font-semibold text-[var(--foreground)]">
            {L.drivers}
          </h3>
          <DriversPanel data={data} />
        </div>
        <div>
          <h3 className="mb-2 text-[14px] font-semibold text-[var(--foreground)]">
            {L.eventRisk}
          </h3>
          <EventRiskPanel data={data} />
        </div>
      </div>

      <AiSynthesisPanel data={data} />

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-2 text-[14px] font-semibold text-[var(--foreground)]">
            {L.uncertainties}
          </h3>
          {data.synthesis.uncertainties.length === 0 ? (
            <p className="text-[13px] text-[var(--muted)]">—</p>
          ) : (
            <ul className="list-disc space-y-1 pl-5 text-[13px] text-[var(--foreground-secondary)]">
              {data.synthesis.uncertainties.map((u: string) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="mb-2 text-[14px] font-semibold text-[var(--foreground)]">
            {L.whatToWatch}
          </h3>
          {data.synthesis.whatToWatch.length === 0 ? (
            <p className="text-[13px] text-[var(--muted)]">—</p>
          ) : (
            <ul className="list-disc space-y-1 pl-5 text-[13px] text-[var(--foreground-secondary)]">
              {data.synthesis.whatToWatch.map((w: string) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-[14px] font-semibold text-[var(--foreground)]">
          {L.sources}
        </h3>
        <SourcesPanel data={data} />
      </div>
    </section>
  );
};

export const MarketContextSection = ({ symbol }: MarketContextSectionProps) => {
  const query = useMarketSynthesis(symbol);
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await tradingRepository.getMarketSynthesis(symbol, {
        forceRefresh: true,
      });
      queryClient.setQueryData(tradingKeys.marketSynthesis(symbol), data);
    } finally {
      setRefreshing(false);
    }
  }, [queryClient, symbol]);

  return (
    <QueryState
      isLoading={query.isLoading}
      isError={query.isError}
      errorMessage={query.error?.message ?? L.unavailable}
      onRetry={() => void query.refetch()}
      loadingFallback={<MarketContextSkeleton />}
      section="bối cảnh thị trường"
    >
      {query.data ? (
        <MarketContextBody
          data={query.data}
          onRefresh={() => void handleRefresh()}
          refreshing={refreshing}
        />
      ) : null}
    </QueryState>
  );
};
