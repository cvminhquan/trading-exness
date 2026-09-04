import { z } from "zod";
import { apiErrorEnvelopeSchema, createDataEnvelopeSchema, createPaginatedEnvelopeSchema } from "@/domain/api/envelope";
import type { DashboardEnv } from "@/lib/config/env";
import {
  createNetworkError,
  createTimeoutError,
  createValidationError,
  normalizeHttpError,
} from "@/lib/api/errors";

export type ApiClientConfig = Pick<DashboardEnv, "apiBaseUrl" | "apiTimeoutMs">;

export type ApiGetOptions = {
  query?: string;
  signal?: AbortSignal;
};

type FetchLike = typeof fetch;

const nativeFetch: FetchLike = (input, init) => globalThis.fetch(input, init);

const isAbortError = (error: unknown): boolean =>
  typeof error === "object" && error !== null && "name" in error && error.name === "AbortError";

export class ApiClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchFn: FetchLike;

  constructor(config: ApiClientConfig, fetchFn: FetchLike = nativeFetch) {
    this.baseUrl = config.apiBaseUrl.replace(/\/$/, "");
    this.timeoutMs = config.apiTimeoutMs;
    this.fetchFn = fetchFn;
  }

  async get<T>(path: string, schema: z.ZodType<T>, options: ApiGetOptions = {}): Promise<T> {
    return this.requestData(path, schema, { method: "GET", ...options });
  }

  async post<T>(
    path: string,
    schema: z.ZodType<T>,
    body: unknown,
    options: ApiGetOptions = {},
  ): Promise<T> {
    return this.requestData(path, schema, { method: "POST", body, ...options });
  }

  private async requestData<T>(
    path: string,
    schema: z.ZodType<T>,
    options: ApiGetOptions & { method: "GET" | "POST"; body?: unknown },
  ): Promise<T> {
    const url = `${this.baseUrl}${path}${options.query ?? ""}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    const signal = options.signal ?? controller.signal;

    let response: Response;
    try {
      const headers: Record<string, string> = { Accept: "application/json" };
      if (options.body !== undefined) {
        headers["Content-Type"] = "application/json";
      }
      response = await this.fetchFn(url, {
        method: options.method,
        headers,
        signal,
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      });
    } catch (error) {
      if (isAbortError(error)) {
        throw createTimeoutError();
      }
      throw createNetworkError(error);
    } finally {
      clearTimeout(timeout);
    }

    let json: unknown;
    try {
      json = await response.json();
    } catch {
      throw normalizeHttpError(response.status);
    }

    if (!response.ok) {
      const parsedError = apiErrorEnvelopeSchema.safeParse(json);
      throw normalizeHttpError(response.status, parsedError.success ? parsedError.data : json);
    }

    const envelopeSchema = createDataEnvelopeSchema(schema);
    const parsed = envelopeSchema.safeParse(json);
    if (!parsed.success) {
      throw createValidationError(parsed.error.flatten());
    }

    return parsed.data.data;
  }

  async getList<T>(path: string, itemSchema: z.ZodType<T>, options: ApiGetOptions = {}): Promise<T[]> {
    const url = `${this.baseUrl}${path}${options.query ?? ""}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    const signal = options.signal ?? controller.signal;

    let response: Response;
    try {
      response = await this.fetchFn(url, {
        method: "GET",
        headers: { Accept: "application/json" },
        signal,
      });
    } catch (error) {
      if (isAbortError(error)) {
        throw createTimeoutError();
      }
      throw createNetworkError(error);
    } finally {
      clearTimeout(timeout);
    }

    let json: unknown;
    try {
      json = await response.json();
    } catch {
      throw normalizeHttpError(response.status);
    }

    if (!response.ok) {
      const parsedError = apiErrorEnvelopeSchema.safeParse(json);
      throw normalizeHttpError(response.status, parsedError.success ? parsedError.data : json);
    }

    const envelopeSchema = createPaginatedEnvelopeSchema(itemSchema);
    const parsed = envelopeSchema.safeParse(json);
    if (!parsed.success) {
      throw createValidationError(parsed.error.flatten());
    }

    return parsed.data.data;
  }
}

export const createApiClient = (config: ApiClientConfig, fetchFn: FetchLike = nativeFetch): ApiClient =>
  new ApiClient(config, fetchFn);
