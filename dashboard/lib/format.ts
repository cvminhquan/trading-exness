import { PNL_LABELS } from "@/lib/i18n/vi";

const UNAVAILABLE = "—";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const compactNumberFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export const formatCurrency = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return currencyFormatter.format(value);
};

export const formatSignedCurrency = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  const formatted = formatCurrency(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
};

export const formatPercent = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return percentFormatter.format(value / 100);
};

export const formatPrice = (
  value: number | null | undefined,
  digits = 2,
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return value.toFixed(digits);
};

export const formatMarketPrice = (
  value: number | null | undefined,
  digits = 5,
): string => formatPrice(value, digits);

export const formatVolume = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return `${compactNumberFormatter.format(value)} lots`;
};

export const formatRMultiple = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}R`;
};

export const formatNumber = (value: number | null | undefined, digits = 2): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return value.toFixed(digits);
};

export const formatDateTime = (iso: string | null | undefined): string => {
  if (!iso) return UNAVAILABLE;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
};

export const formatDuration = (openedAt: string | null | undefined): string => {
  if (!openedAt) return UNAVAILABLE;
  const ms = Date.now() - new Date(openedAt).getTime();
  const hours = Math.floor(ms / 3_600_000);
  const minutes = Math.floor((ms % 3_600_000) / 60_000);
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h`;
  }
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};

export type PnLSentiment = "profit" | "loss" | "flat";

export const getPnLSentiment = (value: number | null | undefined): PnLSentiment => {
  if (value === null || value === undefined || value === 0) return "flat";
  return value > 0 ? "profit" : "loss";
};

export const formatInteger = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return new Intl.NumberFormat("en-US").format(Math.round(value));
};

export const formatDurationBars = (bars: number | null | undefined): string => {
  if (bars === null || bars === undefined || Number.isNaN(bars)) return UNAVAILABLE;
  const hours = Math.round((bars * 15) / 60);
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h (${bars} bars)`;
  }
  return `${hours}h (${bars} bars)`;
};

export const formatDateRange = (
  start: string | null | undefined,
  end: string | null | undefined,
): string => {
  if (!start || !end) return UNAVAILABLE;
  const fmt = (iso: string) =>
    new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" }).format(new Date(iso));
  return `${fmt(start)} → ${fmt(end)}`;
};

export const formatPnLLabel = (value: number | null | undefined): string => {
  const sentiment = getPnLSentiment(value);
  return PNL_LABELS[sentiment];
};
