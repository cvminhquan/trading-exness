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

export class ApiClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchFn: FetchLike;

  constructor(config: ApiClientConfig, fetchFn: FetchLike = fetch) {
    this.baseUrl = config.apiBaseUrl.replace(/\/$/, "");
    this.timeoutMs = config.apiTimeoutMs;
    this.fetchFn = fetchFn;
  }

  async get<T>(path: string, schema: z.ZodType<T>, options: ApiGetOptions = {}): Promise<T> {
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
        cache: "no-store",
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
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
        cache: "no-store",
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
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

export const createApiClient = (config: ApiClientConfig, fetchFn?: FetchLike): ApiClient =>
  new ApiClient(config, fetchFn);
