import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveApiBaseUrl } from "@/lib/config/env";

describe("resolveApiBaseUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("đổi localhost thành 127.0.0.1 khi chạy trên server", () => {
    expect(resolveApiBaseUrl("http://localhost:8000/")).toBe("http://127.0.0.1:8000");
  });

  it("dùng API nội bộ khi env là path rewrite", () => {
    vi.stubEnv("API_INTERNAL_URL", "http://127.0.0.1:8000");
    expect(resolveApiBaseUrl("/engine")).toBe("http://127.0.0.1:8000");
  });

  it("giữ path tương đối khi có window", () => {
    vi.stubGlobal("window", { document: {} });
    expect(resolveApiBaseUrl("/engine")).toBe("/engine");
  });
});
