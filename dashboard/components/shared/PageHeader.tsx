import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type PageHeaderProps = {
  title: string;
  description: string;
  action?: ReactNode;
  badge?: ReactNode;
  className?: string;
};

export const PageHeader = ({
  title,
  description,
  action,
  badge,
  className,
}: PageHeaderProps) => (
  <header
    className={cn(
      "flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between",
      className,
    )}
  >
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold tracking-tight text-slate-900">
          {title}
        </h1>
        {badge}
      </div>
      <p className="mt-0.5 max-w-2xl text-xs text-slate-500">{description}</p>
    </div>
    {action ? <div className="shrink-0">{action}</div> : null}
  </header>
);
