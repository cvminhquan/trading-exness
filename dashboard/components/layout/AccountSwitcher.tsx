"use client";

import { useEffect, useId, useState } from "react";
import type { AccountProfileId } from "@/domain";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/shared/Skeletons";
import { A11Y, ACCOUNT_SWITCH } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";
import { useAccountSwitchState, useSetActiveAccount } from "@/queries/use-trading-queries";

type AccountSwitcherProps = {
  variant?: "compact" | "card";
};

export const AccountSwitcher = ({ variant = "compact" }: AccountSwitcherProps) => {
  const titleId = useId();
  const { data, isLoading } = useAccountSwitchState();
  const mutation = useSetActiveAccount();
  const [pendingLive, setPendingLive] = useState(false);

  const handleSelect = (profile: AccountProfileId) => {
    if (!data || profile === data.activeProfile || mutation.isPending) {
      return;
    }
    const target = data.profiles.find((item) => item.id === profile);
    if (!target?.configured) {
      return;
    }
    if (profile === "live") {
      setPendingLive(true);
      return;
    }
    mutation.mutate(profile);
  };

  const handleConfirmLive = () => {
    setPendingLive(false);
    mutation.mutate("live");
  };

  const handleCancelLive = () => {
    setPendingLive(false);
  };

  useEffect(() => {
    if (!pendingLive) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPendingLive(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pendingLive]);

  if (isLoading && !data) {
    return <Skeleton className={variant === "compact" ? "h-8 w-40" : "h-36 w-full"} />;
  }

  if (!data) {
    return null;
  }

  const demo = data.profiles.find((item) => item.id === "demo");
  const live = data.profiles.find((item) => item.id === "live");
  const active = data.profiles.find((item) => item.id === data.activeProfile);
  const errorMessage = mutation.error?.message;

  const maskLogin = (login: number | null | undefined): string | null => {
    if (login == null) return null;
    const text = String(Math.abs(login));
    return text.length <= 4 ? `***${text}` : `***${text.slice(-4)}`;
  };

  const activeSummary =
    active?.configured && (active.server || active.login != null) ? (
      <span
        className="max-w-[14rem] truncate text-[12px] tabular-nums text-[var(--muted)] sm:max-w-none"
        title={ACCOUNT_SWITCH.activeAccount}
        aria-label={ACCOUNT_SWITCH.activeAccount}
      >
        {[active.server, maskLogin(active.login)].filter(Boolean).join(" · ")}
      </span>
    ) : (
      <span className="text-xs text-slate-400">{ACCOUNT_SWITCH.notConfigured}</span>
    );
  const switcher = (
    <div
      className="inline-flex rounded-[var(--radius-control)] border border-[var(--border-strong)] bg-[var(--surface)] p-0.5 shadow-[var(--shadow-sm)]"
      role="group"
      aria-label={A11Y.accountSwitch}
      title={ACCOUNT_SWITCH.activeAccount}
    >
      <button
        type="button"
        className={cn(
          "rounded-[calc(var(--radius-control)-2px)] px-3 py-1.5 text-[12px] font-semibold transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
          data.activeProfile === "demo"
            ? "bg-[var(--accent)] text-white shadow-[var(--shadow-sm)]"
            : "text-[var(--foreground-secondary)] hover:bg-[var(--accent-subtle)] hover:text-[var(--accent)]",
        )}
        aria-pressed={data.activeProfile === "demo"}
        disabled={!demo?.configured || mutation.isPending}
        title={!demo?.configured ? ACCOUNT_SWITCH.demoNotConfigured : ACCOUNT_SWITCH.demoFull}
        onClick={() => handleSelect("demo")}
      >
        {ACCOUNT_SWITCH.demo}
      </button>
      <button
        type="button"
        className={cn(
          "rounded-[calc(var(--radius-control)-2px)] px-3 py-1.5 text-[12px] font-semibold transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
          data.activeProfile === "live"
            ? "bg-[var(--warning)] text-white shadow-[var(--shadow-sm)]"
            : "text-[var(--foreground-secondary)] hover:bg-[var(--warning-subtle)] hover:text-[var(--warning)]",
          !live?.configured && "cursor-not-allowed opacity-50",
        )}
        aria-pressed={data.activeProfile === "live"}
        disabled={!live?.configured || mutation.isPending}
        title={!live?.configured ? ACCOUNT_SWITCH.liveNotConfigured : ACCOUNT_SWITCH.liveFull}
        onClick={() => handleSelect("live")}
      >
        {ACCOUNT_SWITCH.live}
      </button>
    </div>
  );

  const statusBadge =
    data.activeProfile === "live" ? (
      <Badge variant="warning" className="normal-case">
        {ACCOUNT_SWITCH.liveFull}
      </Badge>
    ) : (
      <Badge variant="info" className="normal-case">
        {ACCOUNT_SWITCH.demoFull}
      </Badge>
    );

  const dialog = pendingLive ? (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/40"
        aria-label={A11Y.closeAccountConfirm}
        onClick={handleCancelLive}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl"
      >
        <h2 id={titleId} className="text-base font-semibold text-slate-900">
          {ACCOUNT_SWITCH.confirmTitle}
        </h2>
        <p className="mt-2 text-sm text-slate-600">{ACCOUNT_SWITCH.confirmBody}</p>
        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={handleCancelLive}>
            {ACCOUNT_SWITCH.cancel}
          </Button>
          <Button type="button" variant="danger" onClick={handleConfirmLive}>
            {ACCOUNT_SWITCH.confirm}
          </Button>
        </div>
      </div>
    </div>
  ) : null;

  if (variant === "compact") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        {switcher}
        {activeSummary}
        {mutation.isPending ? (
          <span className="text-xs text-slate-500">{ACCOUNT_SWITCH.switching}</span>
        ) : null}
        {errorMessage ? <span className="text-xs text-rose-600">{errorMessage}</span> : null}
        {dialog}
      </div>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{ACCOUNT_SWITCH.title}</CardTitle>
          {statusBadge}
        </div>
        <CardDescription>{ACCOUNT_SWITCH.description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          {switcher}
          {mutation.isPending ? (
            <span className="text-sm text-slate-500">{ACCOUNT_SWITCH.switching}</span>
          ) : null}
        </div>
        <dl className="grid gap-3 sm:grid-cols-2">
          {data.profiles.map((profile) => (
            <div key={profile.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <dt className="text-sm font-medium text-slate-900">{profile.label}</dt>
              <dd className="mt-1 space-y-0.5 text-xs text-slate-600">
                <p>
                  {ACCOUNT_SWITCH.login}: {profile.configured ? profile.login : ACCOUNT_SWITCH.notConfigured}
                </p>
                <p>
                  {ACCOUNT_SWITCH.server}: {profile.configured ? profile.server : ACCOUNT_SWITCH.notConfigured}
                </p>
              </dd>
            </div>
          ))}
        </dl>
        {!live?.configured ? (
          <p className="text-xs text-amber-800">{ACCOUNT_SWITCH.liveNotConfigured}</p>
        ) : null}
        {errorMessage ? <p className="text-sm text-rose-600">{errorMessage}</p> : null}
        <p className="text-xs text-slate-500">{data.note}</p>
        {dialog}
      </CardContent>
    </Card>
  );
};
