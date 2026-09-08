import { redirect } from "next/navigation";
import { DEFAULT_DASHBOARD_SYMBOL, dashboardSymbolHref } from "@/lib/symbols/config";

/** /dashboard → default symbol workspace */
export default function DashboardIndexPage() {
  redirect(dashboardSymbolHref(DEFAULT_DASHBOARD_SYMBOL));
}
