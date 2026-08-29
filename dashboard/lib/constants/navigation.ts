import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  LayoutDashboard,
  Settings,
  Shield,
  Target,
  Wallet,
} from "lucide-react";
import { NAV } from "@/lib/i18n/vi";

export type NavItem = {
  id: keyof typeof NAV;
  href: string;
  label: string;
  description: string;
};

export const NAV_ITEMS: NavItem[] = [
  { id: "overview", href: "/dashboard", ...NAV.overview },
  { id: "positions", href: "/dashboard/positions", ...NAV.positions },
  { id: "trades", href: "/dashboard/trades", ...NAV.trades },
  { id: "strategy", href: "/dashboard/strategy", ...NAV.strategy },
  { id: "risk", href: "/dashboard/risk", ...NAV.risk },
  { id: "backtest", href: "/dashboard/backtest", ...NAV.backtest },
  { id: "settings", href: "/dashboard/settings", ...NAV.settings },
];

export const NAV_ICONS: Record<NavItem["id"], LucideIcon> = {
  overview: LayoutDashboard,
  positions: Wallet,
  trades: Activity,
  strategy: Target,
  risk: Shield,
  backtest: BarChart3,
  settings: Settings,
};

export const getNavMeta = (pathname: string): NavItem | undefined =>
  NAV_ITEMS.find((item) => item.href === pathname);
