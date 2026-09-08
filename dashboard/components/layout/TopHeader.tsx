"use client";

import { AccountSwitcher } from "@/components/layout/AccountSwitcher";
import {
  BotStatusIndicator,
  ConnectionIndicator,
} from "@/components/shared/BotStatusIndicator";
import { Skeleton } from "@/components/shared/Skeletons";
import { UI } from "@/lib/i18n/vi";
import { useSessionContext } from "@/queries/use-trading-queries";

export const TopHeader = () => {
  const { data, isLoading } = useSessionContext();

  return (
    <header
      className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--surface)]"
      style={{ boxShadow: "var(--shadow-xs)" }}
    >
      <div className="flex items-center justify-between gap-3 px-4 py-3 md:px-6">
        <p className="truncate text-[15px] font-semibold tracking-tight text-[var(--foreground)] md:text-[16px]">
          {UI.appName}
        </p>

        <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-3">
          <AccountSwitcher variant="compact" />
          {isLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : data ? (
            <>
              <ConnectionIndicator status={data.connectionStatus} compact />
              <BotStatusIndicator status={data.botStatus} compact />
            </>
          ) : null}
        </div>
      </div>
    </header>
  );
};
