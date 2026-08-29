import { cn } from "@/lib/utils";

export const Skeleton = ({ className }: { className?: string }) => (
  <div className={cn("animate-pulse rounded-md bg-slate-200", className)} aria-hidden />
);

export const MetricCardSkeleton = () => (
  <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
    <Skeleton className="mb-3 h-3 w-24" />
    <Skeleton className="h-8 w-32" />
    <Skeleton className="mt-2 h-3 w-20" />
  </div>
);

export const MetricGridSkeleton = ({ count = 4 }: { count?: number }) => (
  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
    {Array.from({ length: count }).map((_, i) => (
      <MetricCardSkeleton key={i} />
    ))}
  </div>
);

export const ChartSkeleton = ({ height = "h-72" }: { height?: string }) => (
  <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
    <Skeleton className="mb-4 h-4 w-36" />
    <Skeleton className={cn("w-full", height)} />
  </div>
);

export const TableSkeleton = ({ rows = 5 }: { rows?: number }) => (
  <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
    <Skeleton className="mb-4 h-4 w-40" />
    <div className="space-y-3">
      <Skeleton className="h-8 w-full" />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  </div>
);

export const OverviewSkeleton = () => (
  <div className="space-y-6">
    <MetricGridSkeleton count={8} />
    <ChartSkeleton />
    <TableSkeleton rows={3} />
  </div>
);
