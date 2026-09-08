import { PNL_LABELS } from "@/lib/i18n/vi";

const UNAVAILABLE = "—";

const moneyFormatter = (currency: string, digits = 2) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

const numberFormatter = (digits = 2) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
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

/** Account/instrument money — uses ISO currency when provided. */
export const formatMoney = (
  value: number | null | undefined,
  currency = "USD",
  digits = 2,
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  try {
    return moneyFormatter(currency, digits).format(value);
  } catch {
    return `${numberFormatter(digits).format(value)} ${currency}`;
  }
};

export const formatCurrency = (value: number | null | undefined): string =>
  formatMoney(value, "USD");

export const formatSignedMoney = (
  value: number | null | undefined,
  currency = "USD",
  digits = 2,
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  const abs = formatMoney(Math.abs(value), currency, digits);
  if (value > 0) return `+${abs}`;
  if (value < 0) return `-${abs}`;
  return abs;
};

export const formatSignedCurrency = (value: number | null | undefined): string =>
  formatSignedMoney(value, "USD");

/** `value` is already in percent units (e.g. 0.30 for 0.30%). */
export const formatSignedPercent = (
  value: number | null | undefined,
  digits = 2,
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
};

/** Alias used by market lists. */
export const formatSignedPercentChange = formatSignedPercent;

/** `value` is percent units; formats via Intl as ratio when needed. */
export const formatPercent = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return percentFormatter.format(value / 100);
};

export const formatPrice = (
  value: number | null | undefined,
  digits = 2,
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return numberFormatter(digits).format(value);
};

export const formatMarketPrice = (
  value: number | null | undefined,
  digits = 2,
): string => formatPrice(value, digits);

/** Compact market list price — en-US tabular. */
export const formatCompactMarketPrice = (
  value: number | null | undefined,
  digits = 2,
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) {
    return `${numberFormatter(2).format(value / 1_000_000_000)}B`;
  }
  if (abs >= 1_000_000) {
    return `${numberFormatter(2).format(value / 1_000_000)}M`;
  }
  return numberFormatter(Math.min(digits, abs >= 100 ? 2 : digits)).format(value);
};

export const formatVolume = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return `${compactNumberFormatter.format(value)} lot`;
};

export const formatScore = (value: number | null | undefined, digits = 2): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return numberFormatter(digits).format(value);
};

export const formatRMultiple = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}R`;
};

export const formatNumber = (value: number | null | undefined, digits = 2): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;
  return numberFormatter(digits).format(value);
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
