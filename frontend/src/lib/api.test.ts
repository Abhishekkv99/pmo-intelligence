import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import {
  api,
  ApiError,
  REFRESH_TIMEOUT_MS,
  refreshAccessToken,
  setSessionExpiredHandler,
} from "./api";
import { getToken, removeToken, setToken } from "./auth-token";

function json(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

function calls(): string[] {
  return fetchMock.mock.calls.map(([url]) =>
    String(url).replace(/^.*\/api\/v1/, ""),
  );
}

describe("ApiClient 401 handling", () => {
  const expired = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    expired.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setToken("old-token");
    setSessionExpiredHandler(expired);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    setSessionExpiredHandler(null);
    removeToken();
  });

  it("refreshes once and retries with the new token", async () => {
    fetchMock
      .mockResolvedValueOnce(json(401))
      .mockResolvedValueOnce(json(200, { access_token: "new-token" }))
      .mockResolvedValueOnce(json(200, { ok: true }));

    await expect(api.get("/dashboard/stats")).resolves.toEqual({ ok: true });

    expect(calls()).toEqual([
      "/dashboard/stats",
      "/auth/refresh",
      "/dashboard/stats",
    ]);
    const retryInit = fetchMock.mock.calls[2][1] as RequestInit;
    expect((retryInit.headers as Record<string, string>).Authorization).toBe(
      "Bearer new-token",
    );
    expect(expired).not.toHaveBeenCalled();
  });

  it("gives up after one retry instead of refreshing in a loop", async () => {
    fetchMock
      .mockResolvedValueOnce(json(401))
      .mockResolvedValueOnce(json(200, { access_token: "new-token" }))
      .mockResolvedValueOnce(json(401, { detail: "Not authenticated" }));

    await expect(api.get("/interviews")).rejects.toMatchObject({ status: 401 });

    expect(calls()).toEqual(["/interviews", "/auth/refresh", "/interviews"]);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(getToken()).toBeNull();
  });

  it("expires the session when the refresh is refused", async () => {
    fetchMock.mockResolvedValueOnce(json(401)).mockResolvedValueOnce(json(401));

    await expect(api.get("/interviews")).rejects.toBeInstanceOf(ApiError);

    expect(calls()).toEqual(["/interviews", "/auth/refresh"]);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(getToken()).toBeNull();
  });

  it("times out a refresh that never answers", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );

    const result = refreshAccessToken();
    await vi.advanceTimersByTimeAsync(REFRESH_TIMEOUT_MS);

    await expect(result).resolves.toBe(false);
  });

  it("shares one refresh between concurrent 401s", async () => {
    fetchMock.mockImplementation(async (url) => {
      if (String(url).endsWith("/auth/refresh")) {
        return json(200, { access_token: "new-token" });
      }
      const init = fetchMock.mock.calls.at(-1)?.[1] as RequestInit;
      const auth = (init.headers as Record<string, string>).Authorization;
      return auth === "Bearer new-token" ? json(200, { ok: true }) : json(401);
    });

    await Promise.all([api.get("/a"), api.get("/b"), api.get("/c")]);

    expect(calls().filter((c) => c === "/auth/refresh")).toHaveLength(1);
    expect(expired).not.toHaveBeenCalled();
  });

  it("never refreshes for the login and refresh endpoints themselves", async () => {
    fetchMock.mockResolvedValueOnce(
      json(401, { detail: "Invalid credentials" }),
    );

    await expect(api.post("/auth/login", { email: "a" })).rejects.toMatchObject(
      {
        status: 401,
      },
    );

    expect(calls()).toEqual(["/auth/login"]);
    expect(expired).not.toHaveBeenCalled();
  });
});
