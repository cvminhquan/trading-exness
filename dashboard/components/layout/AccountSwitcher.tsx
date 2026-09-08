"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
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
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const { data, isLoading } = useAccountSwitchState();
  const mutation = useSetActiveAccount();
  const [pendingLive, setPendingLive] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isSwitching, setIsSwitching] = useState(false);

  const runSwitch = (profile: AccountProfileId) => {
    setIsSwitching(true);
    setMenuOpen(false);
    mutation.mutate(profile, {
      onSettled: () => setIsSwitching(false),
    });
  };

  const handleSelect = (profile: AccountProfileId) => {
    if (!data || profile === data.activeProfile || isSwitching || mutation.isPending) {
      setMenuOpen(false);
      return;
    }
    const target = data.profiles.find((item) => item.id === profile);
    if (!target?.configured) {
      return;
    }
    setMenuOpen(false);
    if (profile === "live") {
      setPendingLive(true);
      return;
    }
    runSwitch(profile);
  };

  const handleConfirmLive = () => {
    setPendingLive(false);
    runSwitch("live");
  };

  const handleCancelLive = () => {
    if (isSwitching) return;
    setPendingLive(false);
  };

  useEffect(() => {
    if (!pendingLive && !menuOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isSwitching) {
        setPendingLive(false);
        setMenuOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pendingLive, menuOpen, isSwitching]);

  useEffect(() => {
    if (!menuOpen || isSwitching) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, [menuOpen, isSwitching]);

  useEffect(() => {
    if (!isSwitching) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isSwitching]);

  if (isLoading && !data) {
    return <Skeleton className={variant === "compact" ? "h-8 w-28" : "h-36 w-full"} />;
  }

  if (!data) {
    return null;
  }

  const demo = data.profiles.find((item) => item.id === "demo");
  const live = data.profiles.find((item) => item.id === "live");
  const active = data.profiles.find((item) => item.id === data.activeProfile);
  const errorMessage = mutation.error?.message;
  const isLive = data.activeProfile === "live";
  const busy = isSwitching || mutation.isPending;

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
      <span className="text-xs text-[var(--muted)]">{ACCOUNT_SWITCH.notConfigured}</span>
    );

  const pillLabel = isLive ? ACCOUNT_SWITCH.livePill : ACCOUNT_SWITCH.demoPill;

  const switchingOverlay = busy ? (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/45 p-4"
      role="alertdialog"
      aria-modal="true"
      aria-busy="true"
      aria-live="assertive"
      aria-label={ACCOUNT_SWITCH.switchingAria}
    >
      <div className="flex max-w-sm flex-col items-center gap-3 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5 text-center shadow-[var(--shadow-card)]">
        <Loader2
          className="h-8 w-8 animate-spin text-[var(--accent)]"
          aria-hidden
          strokeWidth={2.25}
        />
        <p className="text-[15px] font-semibold text-[var(--foreground)]">
          {ACCOUNT_SWITCH.switching}
        </p>
        <p className="text-[13px] text-[var(--foreground-secondary)]">
          {ACCOUNT_SWITCH.switchingHint}
        </p>
      </div>
    </div>
  ) : null;

  const switcher = (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className={cn(
          "inline-flex h-8 items-center gap-1 rounded-full px-3 text-[12px] font-bold tracking-wide uppercase transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
          isLive
            ? "bg-[var(--warning-subtle)] text-[var(--warning)] hover:brightness-[0.98]"
            : "bg-[var(--accent-subtle)] text-[var(--accent)] hover:bg-[var(--accent-muted)]",
          busy && "cursor-wait opacity-70",
        )}
        aria-haspopup="listbox"
        aria-expanded={menuOpen}
        aria-controls={menuId}
        aria-label={A11Y.accountSwitch}
        title={isLive ? ACCOUNT_SWITCH.liveFull : ACCOUNT_SWITCH.demoFull}
        disabled={busy}
        onClick={() => setMenuOpen((open) => !open)}
      >
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        ) : null}
        {pillLabel}
        <ChevronDown
          className={cn("h-3.5 w-3.5 transition-transform", menuOpen && "rotate-180")}
          aria-hidden
          strokeWidth={2.5}
        />
      </button>

      {menuOpen && !busy ? (
        <ul
          id={menuId}
          role="listbox"
          aria-label={A11Y.accountSwitch}
          className="absolute top-[calc(100%+6px)] right-0 z-30 min-w-[11rem] overflow-hidden rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] py-1 shadow-[var(--shadow-card)]"
        >
          <li role="option" aria-selected={data.activeProfile === "demo"}>
            <button
              type="button"
              className={cn(
                "flex w-full items-center justify-between px-3 py-2 text-left text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:bg-[var(--accent-subtle)]",
                data.activeProfile === "demo"
                  ? "bg-[var(--accent-subtle)] text-[var(--accent)]"
                  : "text-[var(--foreground)] hover:bg-[var(--surface-subtle)]",
                !demo?.configured && "cursor-not-allowed opacity-50",
              )}
              disabled={!demo?.configured || busy}
              title={!demo?.configured ? ACCOUNT_SWITCH.demoNotConfigured : ACCOUNT_SWITCH.demoFull}
              onClick={() => handleSelect("demo")}
            >
              <span>{ACCOUNT_SWITCH.demoPill}</span>
              {data.activeProfile === "demo" ? (
                <span className="text-[11px] text-[var(--accent)]">{ACCOUNT_SWITCH.activeMark}</span>
              ) : null}
            </button>
          </li>
          <li role="option" aria-selected={data.activeProfile === "live"}>
            <button
              type="button"
              className={cn(
                "flex w-full items-center justify-between px-3 py-2 text-left text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:bg-[var(--warning-subtle)]",
                data.activeProfile === "live"
                  ? "bg-[var(--warning-subtle)] text-[var(--warning)]"
                  : "text-[var(--foreground)] hover:bg-[var(--surface-subtle)]",
                !live?.configured && "cursor-not-allowed opacity-50",
              )}
              disabled={!live?.configured || busy}
              title={!live?.configured ? ACCOUNT_SWITCH.liveNotConfigured : ACCOUNT_SWITCH.liveFull}
              onClick={() => handleSelect("live")}
            >
              <span>{ACCOUNT_SWITCH.livePill}</span>
              {data.activeProfile === "live" ? (
                <span className="text-[11px] text-[var(--warning)]">{ACCOUNT_SWITCH.activeMark}</span>
              ) : null}
            </button>
          </li>
        </ul>
      ) : null}
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

  const dialog = pendingLive && !busy ? (
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
        className="relative z-10 w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[var(--shadow-card)]"
      >
        <h2 id={titleId} className="text-base font-semibold text-[var(--foreground)]">
          {ACCOUNT_SWITCH.confirmTitle}
        </h2>
        <p className="mt-2 text-sm text-[var(--foreground-secondary)]">
          {ACCOUNT_SWITCH.confirmBody}
        </p>
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
        {errorMessage && !busy ? (
          <span className="text-xs text-[var(--negative)]">{errorMessage}</span>
        ) : null}
        {dialog}
        {switchingOverlay}
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
        <div className="flex flex-wrap items-center gap-3">{switcher}</div>
        <dl className="grid gap-3 sm:grid-cols-2">
          {data.profiles.map((profile) => (
            <div
              key={profile.id}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] p-3"
            >
              <dt className="text-sm font-medium text-[var(--foreground)]">{profile.label}</dt>
              <dd className="mt-1 space-y-0.5 text-xs text-[var(--foreground-secondary)]">
                <p>
                  {ACCOUNT_SWITCH.login}:{" "}
                  {profile.configured ? profile.login : ACCOUNT_SWITCH.notConfigured}
                </p>
                <p>
                  {ACCOUNT_SWITCH.server}:{" "}
                  {profile.configured ? profile.server : ACCOUNT_SWITCH.notConfigured}
                </p>
              </dd>
            </div>
          ))}
        </dl>
        {!live?.configured ? (
          <p className="text-xs text-[var(--warning)]">{ACCOUNT_SWITCH.liveNotConfigured}</p>
        ) : null}
        {errorMessage && !busy ? (
          <p className="text-sm text-[var(--negative)]">{errorMessage}</p>
        ) : null}
        <p className="text-xs text-[var(--muted)]">{data.note}</p>
        {dialog}
        {switchingOverlay}
      </CardContent>
    </Card>
  );
};
