export type DataSource = "mock" | "api";

const DEFAULT_API_BASE_URL = "/engine";
const DEFAULT_DATA_SOURCE: DataSource = "mock";
const DEFAULT_API_TIMEOUT_MS = 15_000;
const DEFAULT_API_INTERNAL_URL = "http://127.0.0.1:8000";

export type DashboardEnv = {
  dataSource: DataSource;
  apiBaseUrl: string;
  apiTimeoutMs: number;
};

const parseDataSource = (value: string | undefined): DataSource => {
  if (value === "api") return "api";
  return DEFAULT_DATA_SOURCE;
};

const forceIpv4Loopback = (url: string): string => url.replace("://localhost", "://127.0.0.1");

/**
 * Browser: path `/engine` (cùng origin, Next rewrite).
 * Server: gọi thẳng API IPv4 để tránh [::1] và tránh SSR fetch chính mình.
 */
export const resolveApiBaseUrl = (apiBaseUrl: string): string => {
  const trimmed = apiBaseUrl.replace(/\/$/, "");
  const internalUrl = (process.env.API_INTERNAL_URL ?? DEFAULT_API_INTERNAL_URL).replace(/\/$/, "");

  if (typeof window === "undefined") {
    if (/^https?:\/\//i.test(trimmed)) {
      return forceIpv4Loopback(trimmed);
    }
    return internalUrl;
  }

  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }

  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
};

export const getDashboardEnv = (): DashboardEnv => ({
  dataSource: parseDataSource(process.env.NEXT_PUBLIC_DATA_SOURCE),
  apiBaseUrl: resolveApiBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL),
  apiTimeoutMs: DEFAULT_API_TIMEOUT_MS,
});

export const isApiDataSource = (): boolean => getDashboardEnv().dataSource === "api";
