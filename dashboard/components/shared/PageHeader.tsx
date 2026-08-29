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
  <header className={cn("flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between", className)}>
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-50">{title}</h1>
        {badge}
      </div>
      <p className="max-w-3xl text-sm leading-relaxed text-slate-400">{description}</p>
    </div>
    {action ? <div className="shrink-0">{action}</div> : null}
  </header>
);
