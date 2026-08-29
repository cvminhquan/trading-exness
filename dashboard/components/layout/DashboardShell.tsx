"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Menu, X } from "lucide-react";
import { TopHeader } from "@/components/layout/TopHeader";
import { NAV_ICONS, NAV_ITEMS } from "@/lib/constants/navigation";
import { A11Y, UI } from "@/lib/i18n/vi";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export const DashboardShell = ({ children }: { children: React.ReactNode }) => {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navLink = (href: string, id: (typeof NAV_ITEMS)[number]["id"], label: string, onNavigate?: () => void) => {
    const active = pathname === href;
    const Icon = NAV_ICONS[id];
    return (
      <Link
        key={href}
        href={href}
        onClick={onNavigate}
        className={cn(
          "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500",
          active
            ? "bg-slate-800 text-white"
            : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100",
        )}
        aria-current={active ? "page" : undefined}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden />
        {label}
      </Link>
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-[1600px]">
        <aside className="hidden w-60 shrink-0 border-r border-slate-800/80 bg-slate-900/30 md:flex md:flex-col">
          <div className="border-b border-slate-800/80 px-4 py-5">
            <p className="text-sm font-semibold text-slate-100">{UI.navigation}</p>
            <p className="text-xs text-slate-500">{UI.navigationSubtitle}</p>
          </div>
          <nav aria-label={A11Y.mainNav} className="flex-1 space-y-1 p-3">
            {NAV_ITEMS.map(({ href, id, label }) => navLink(href, id, label))}
          </nav>
        </aside>

        {mobileOpen ? (
          <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true">
            <button
              type="button"
              className="absolute inset-0 bg-slate-950/70"
              aria-label={A11Y.closeNav}
              onClick={() => setMobileOpen(false)}
            />
            <div className="absolute left-0 top-0 h-full w-[min(18rem,85vw)] border-r border-slate-800 bg-slate-900 p-4 shadow-xl">
              <div className="mb-4 flex items-center justify-between">
                <p className="text-sm font-semibold">{UI.menu}</p>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={A11Y.closeMenu}
                  onClick={() => setMobileOpen(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <nav aria-label={A11Y.mobileNav} className="space-y-1">
                {NAV_ITEMS.map(({ href, id, label }) =>
                  navLink(href, id, label, () => setMobileOpen(false)),
                )}
              </nav>
            </div>
          </div>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-slate-800/80 px-4 py-2 md:hidden">
            <Button
              variant="outline"
              size="icon"
              aria-label={A11Y.openNav}
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </Button>
            <p className="text-sm font-medium text-slate-300">
              {NAV_ITEMS.find((n) => n.href === pathname)?.label ?? UI.appName}
            </p>
          </div>

          <TopHeader />
          <main className="flex-1 px-4 py-6 md:px-6 lg:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
};
