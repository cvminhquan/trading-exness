import type { Direction, SignalAction } from "@/domain";
import { Badge } from "@/components/ui/badge";
import { DIRECTION_LABELS } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

type DirectionIndicatorProps = {
  direction: Direction | SignalAction;
  className?: string;
};

const resolveMeta = (direction: Direction | SignalAction) => {
  if (direction === "LONG" || direction === "BUY") {
    return {
      label: direction === "BUY" ? DIRECTION_LABELS.BUY : DIRECTION_LABELS.LONG,
      variant: "success" as const,
      Icon: ArrowUpRight,
    };
  }
  if (direction === "SHORT" || direction === "SELL") {
    return {
      label: direction === "SELL" ? DIRECTION_LABELS.SELL : DIRECTION_LABELS.SHORT,
      variant: "danger" as const,
      Icon: ArrowDownRight,
    };
  }
  return { label: DIRECTION_LABELS.HOLD, variant: "default" as const, Icon: Minus };
};

export const DirectionIndicator = ({ direction, className }: DirectionIndicatorProps) => {
  const meta = resolveMeta(direction);
  const Icon = meta.Icon;
  return (
    <Badge variant={meta.variant} className={cn("gap-1 normal-case", className)}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      <span>{meta.label}</span>
    </Badge>
  );
};
