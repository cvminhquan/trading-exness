import type { Quote, QuoteFreshness } from "@/domain";

export const aggregateQuoteFreshness = (quotes: Quote[]): QuoteFreshness => {
  if (quotes.length === 0) {
    return "UNAVAILABLE";
  }
  const gold = quotes.find((quote) => quote.symbol === "XAUUSD");
  if (gold) {
    if (!gold.available || gold.freshness === "UNAVAILABLE") {
      return "UNAVAILABLE";
    }
    return gold.freshness;
  }
  if (quotes.some((quote) => quote.freshness === "LIVE" && quote.available)) {
    return "LIVE";
  }
  if (quotes.some((quote) => quote.freshness === "STALE" && quote.available)) {
    return "STALE";
  }
  return "UNAVAILABLE";
};
