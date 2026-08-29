import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type MetricCardProps = {
  label: string;
  value: string;
  secondaryValue?: string;
  hint?: string;
  trend?: "up" | "down" | "neutral";
  status?: "normal" | "warning" | "critical";
  tooltip?: string;
  className?: string;
  valueClassName?: string;
};

export const MetricCard = ({
  label,
  value,
  secondaryValue,
  hint,
  trend = "neutral",
  status = "normal",
  tooltip,
  className,
  valueClassName,
}: MetricCardProps) => (
  <Card
    className={cn(
      status === "warning" && "border-amber-300",
      status === "critical" && "border-rose-300",
      className,
    )}
  >
    <CardHeader className="pb-2">
      <CardTitle
        className="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500"
        title={tooltip}
      >
        {label}
      </CardTitle>
    </CardHeader>
    <CardContent>
      <div className="flex items-baseline gap-2">
        <p
          className={cn(
            "text-2xl font-semibold tabular-nums tracking-tight text-slate-900",
            trend === "up" && "text-emerald-600",
            trend === "down" && "text-rose-600",
            valueClassName,
          )}
        >
          {value}
        </p>
        {secondaryValue ? (
          <p className="text-sm tabular-nums text-slate-500">{secondaryValue}</p>
        ) : null}
      </div>
      {hint ? <p className="mt-1.5 text-xs leading-relaxed text-slate-500">{hint}</p> : null}
    </CardContent>
  </Card>
);

type MetricStripProps = {
  children: ReactNode;
  className?: string;
};

export const MetricStrip = ({ children, className }: MetricStripProps) => (
  <section className={cn("grid gap-3 sm:grid-cols-2 xl:grid-cols-4", className)}>
    {children}
  </section>
);
