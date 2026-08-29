"use client";

import { PageHeader } from "@/components/shared/PageHeader";
import { QueryState } from "@/components/shared/States";
import { TableSkeleton } from "@/components/shared/Skeletons";
import { PositionTable } from "@/components/positions/PositionTable";
import { EMPTY, NAV, SECTION_LABELS } from "@/lib/i18n/vi";
import { usePositions } from "@/queries/use-trading-queries";

export default function PositionsPage() {
  const { data, isLoading, isError, error, refetch } = usePositions();

  return (
    <div className="space-y-6">
      <PageHeader
        title={NAV.positions.label}
        description={NAV.positions.description}
      />

      <QueryState
        isLoading={isLoading}
        isError={isError}
        errorMessage={error?.message}
        isEmpty={!!data && data.length === 0}
        emptyTitle={EMPTY.noOpenPositions}
        emptyDescription={EMPTY.noOpenPositionsPage}
        onRetry={() => void refetch()}
        loadingFallback={<TableSkeleton rows={4} />}
        section={SECTION_LABELS.positions}
      >
        {data ? <PositionTable positions={data} /> : null}
      </QueryState>
    </div>
  );
}
