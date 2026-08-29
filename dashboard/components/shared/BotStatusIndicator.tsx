import type { BotStatus, ConnectionStatus } from "@/domain";
import { Badge } from "@/components/ui/badge";
import {
  BOT_STATUS_DESCRIPTIONS,
  BOT_STATUS_LABELS,
  CONNECTION_LABELS,
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
    <Badge variant={meta.variant} className={cn("gap-1.5 normal-case", className)}>
      <span className="sr-only">{BOT_STATUS_DESCRIPTIONS[status]}</span>
      <span aria-hidden className="inline-block h-2 w-2 rounded-full bg-current opacity-90" />
      {!compact ? BOT_STATUS_LABELS[status] : status}
    </Badge>
  );
};

type ConnectionIndicatorProps = {
  status: ConnectionStatus;
  className?: string;
};

export const ConnectionIndicator = ({ status, className }: ConnectionIndicatorProps) => {
  const meta = CONNECTION_VARIANT[status];
  return (
    <Badge variant={meta.variant} className={cn("normal-case", className)}>
      {CONNECTION_LABELS[status]}
    </Badge>
  );
};

/** @deprecated Use BotStatusIndicator */
export const StatusBadge = ({ status }: { status: BotStatus; label?: string }) => (
  <BotStatusIndicator status={status} />
);
