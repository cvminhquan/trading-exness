import type { BotStatus, ConnectionStatus, QuoteFreshness } from "@/domain";
import { Badge } from "@/components/ui/badge";
import {
  BOT_STATUS_DESCRIPTIONS,
  BOT_STATUS_LABELS,
  CONNECTION_LABELS,
  QUOTE_FRESHNESS_LABELS,
} from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";

const BOT_STATUS_VARIANT: Record<
  BotStatus,
  { variant: "success" | "default" | "danger" | "warning" }
> = {
  RUNNING: { variant: "success" },
  STOPPED: { variant: "default" },
  ERROR: { variant: "danger" },
  DISCONNECTED: { variant: "warning" },
};

const CONNECTION_VARIANT: Record<
  ConnectionStatus,
  { variant: "success" | "warning" | "danger" }
> = {
  CONNECTED: { variant: "success" },
  RECONNECTING: { variant: "warning" },
  DISCONNECTED: { variant: "danger" },
};

type BotStatusIndicatorProps = {
  status: BotStatus;
  compact?: boolean;
  className?: string;
};

export const BotStatusIndicator = ({ status, compact = false, className }: BotStatusIndicatorProps) => {
  const meta = BOT_STATUS_VARIANT[status];
  return (
    <Badge
      variant={meta.variant}
      className={cn("pointer-events-none normal-case", className)}
      role="status"
    >
      <span className="sr-only">{BOT_STATUS_DESCRIPTIONS[status]}</span>
      <span aria-hidden className="inline-block h-2 w-2 rounded-full bg-current opacity-90" />
      {!compact ? BOT_STATUS_LABELS[status] : BOT_STATUS_LABELS[status]}
    </Badge>
  );
};

type ConnectionIndicatorProps = {
  status: ConnectionStatus;
  className?: string;
  compact?: boolean;
};

export const ConnectionIndicator = ({
  status,
  className,
  compact = false,
}: ConnectionIndicatorProps) => {
  const meta = CONNECTION_VARIANT[status];
  const label = CONNECTION_LABELS[status];
  return (
    <Badge
      variant={meta.variant}
      className={cn("pointer-events-none normal-case", className)}
      title={label}
      aria-label={label}
      role="status"
    >
      <span aria-hidden className="inline-block h-2 w-2 rounded-full bg-current opacity-90" />
      {compact ? label : label}
    </Badge>
  );
};

const FRESHNESS_VARIANT: Record<QuoteFreshness, "success" | "warning" | "danger"> = {
  LIVE: "success",
  STALE: "warning",
  UNAVAILABLE: "danger",
};

type FreshnessIndicatorProps = {
  freshness: QuoteFreshness;
  className?: string;
};

export const FreshnessIndicator = ({ freshness, className }: FreshnessIndicatorProps) => (
  <Badge variant={FRESHNESS_VARIANT[freshness]} className={cn("normal-case", className)}>
    {freshness === "LIVE" ? (
      <span className="mr-1.5 inline-block h-2 w-2 animate-pulse rounded-full bg-current" aria-hidden />
    ) : (
      <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-current" aria-hidden />
    )}
    {QUOTE_FRESHNESS_LABELS[freshness]}
  </Badge>
);

/** @deprecated Use BotStatusIndicator */
export const StatusBadge = ({ status }: { status: BotStatus; label?: string }) => (
  <BotStatusIndicator status={status} />
);
