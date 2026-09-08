"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Hexagon, Menu, X } from "lucide-react";
import { TopHeader } from "@/components/layout/TopHeader";
import { NAV_ICONS, NAV_ITEMS, getNavMeta } from "@/lib/constants/navigation";
import { A11Y, UI } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const NAV_GROUPS: {
  label: string;
  ids: Array<(typeof NAV_ITEMS)[number]["id"]>;
}[] = [
  {
    label: UI.navGroupTrading,
    ids: ["overview", "positions", "trades", "strategy", "risk"],
  },
  {
    label: UI.navGroupResearch,
    ids: ["backtest", "paper"],
  },
  {
    label: UI.navGroupSystem,
    ids: ["settings"],
  },
];

export const DashboardShell = ({ children }: { children: React.ReactNode }) => {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (id: (typeof NAV_ITEMS)[number]["id"], href: string) => {
    if (id === "overview") {
      return (
        pathname === "/dashboard" ||
        (/^\/dashboard\/[A-Za-z0-9]+$/.test(pathname) &&
          ![
            "positions",
            "trades",
            "strategy",
            "risk",
            "backtest",
            "paper",
            "settings",
          ].includes(pathname.split("/")[2]?.toLowerCase() ?? ""))
      );
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const navLink = (
    href: string,
    id: (typeof NAV_ITEMS)[number]["id"],
    label: string,
    onNavigate?: () => void,
  ) => {
    const active = isActive(id, href);
    const Icon = NAV_ICONS[id];
    return (
      <Link
        key={href}
        href={href}
        onClick={onNavigate}
        className={cn(
          "relative flex h-11 items-center gap-3 rounded-r-[var(--radius-tab)] border-l-[3px] px-3 text-[15px] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
          active
            ? "border-[var(--accent)] bg-[var(--surface-active)] font-semibold text-[var(--accent)]"
            : "border-transparent font-medium text-[var(--foreground-secondary)] hover:bg-[var(--accent-subtle)] hover:text-[var(--foreground)]",
        )}
        aria-current={active ? "page" : undefined}
      >
        <Icon
          className={cn(
            "h-[18px] w-[18px] shrink-0",
            active ? "text-[var(--accent)]" : "text-[var(--muted)]",
          )}
          aria-hidden
        />
        {label}
      </Link>
    );
  };

  const navSections = (
    <div className="flex flex-col gap-4 py-3">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="mb-1 px-3 text-[11px] font-semibold tracking-wide text-[var(--muted)] uppercase">
            {group.label}
          </p>
          <div className="flex flex-col gap-0.5">
            {group.ids.map((id) => {
              const item = NAV_ITEMS.find((n) => n.id === id);
              if (!item) return null;
              return navLink(item.href, item.id, item.label);
            })}
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <div className="mx-auto flex min-h-screen">
        <aside className="hidden w-60 shrink-0 border-r border-[var(--border)] bg-[var(--surface)] md:flex md:flex-col">
          <div className="border-b border-[var(--border)] px-4 py-4">
            <div className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-control)] bg-[var(--accent)] text-white shadow-[var(--shadow-sm)]">
                <Hexagon className="h-5 w-5" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="truncate text-[15px] font-semibold text-[var(--foreground)]">
                  {UI.appName}
                </p>
                <p className="truncate text-[12px] text-[var(--muted)]">
                  {UI.productTagline}
                </p>
              </div>
            </div>
          </div>
          <nav aria-label={A11Y.mainNav} className="flex-1 overflow-y-auto px-1">
            {navSections}
          </nav>
        </aside>

        {mobileOpen ? (
          <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true">
            <button
              type="button"
              className="absolute inset-0 bg-slate-900/40"
              aria-label={A11Y.closeNav}
              onClick={() => setMobileOpen(false)}
            />
            <div className="absolute top-0 left-0 h-full w-[min(18rem,85vw)] border-r border-[var(--border)] bg-[var(--surface)] p-3 shadow-[var(--shadow-card)]">
              <div className="mb-3 flex items-center justify-between px-1">
                <p className="text-[15px] font-semibold">{UI.menu}</p>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={A11Y.closeMenu}
                  onClick={() => setMobileOpen(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <nav aria-label={A11Y.mobileNav}>
                {NAV_ITEMS.map(({ href, id, label }) =>
                  navLink(href, id, label, () => setMobileOpen(false)),
                )}
              </nav>
            </div>
          </div>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[var(--surface)] px-4 py-2 md:hidden">
            <Button
              variant="outline"
              size="icon"
              aria-label={A11Y.openNav}
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </Button>
            <p className="text-[15px] font-semibold text-[var(--foreground)]">
              {getNavMeta(pathname)?.label ?? UI.appName}
            </p>
          </div>

          <TopHeader />
          <main className="flex-1 bg-[var(--background)] px-4 py-5 md:px-6 lg:px-8">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
};
