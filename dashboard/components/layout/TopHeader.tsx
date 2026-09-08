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
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 md:px-6">
        <p className="truncate text-sm font-semibold tracking-tight text-slate-900 md:text-base">
          {UI.appName}
        </p>

        <div className="flex flex-wrap items-center justify-end gap-1.5 sm:gap-2">
          <AccountSwitcher variant="compact" />
          {isLoading ? (
            <Skeleton className="h-7 w-16" />
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
