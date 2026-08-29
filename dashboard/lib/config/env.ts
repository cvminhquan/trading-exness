export type DataSource = "mock" | "api";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const DEFAULT_DATA_SOURCE: DataSource = "mock";
const DEFAULT_API_TIMEOUT_MS = 15_000;

export type DashboardEnv = {
  dataSource: DataSource;
  apiBaseUrl: string;
  apiTimeoutMs: number;
};

const parseDataSource = (value: string | undefined): DataSource => {
  if (value === "api") return "api";
  return DEFAULT_DATA_SOURCE;
};

export const getDashboardEnv = (): DashboardEnv => ({
  dataSource: parseDataSource(process.env.NEXT_PUBLIC_DATA_SOURCE),
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL,
  apiTimeoutMs: DEFAULT_API_TIMEOUT_MS,
});

export const isApiDataSource = (): boolean => getDashboardEnv().dataSource === "api";
