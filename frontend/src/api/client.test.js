import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SESSION_EXPIRED_EVENT, apiRequest } from "./client";
import { getAccessToken, getRefreshToken, setTokens } from "./tokenStorage";

function json(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

let fetchMock;
let expired;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  expired = vi.fn();
  window.addEventListener(SESSION_EXPIRED_EVENT, expired);
  setTokens({ access_token: "old-access", refresh_token: "old-refresh" }, { remember: true });
});

afterEach(() => {
  window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  vi.unstubAllGlobals();
});

const callsTo = (path) => fetchMock.mock.calls.filter(([url]) => url.endsWith(path));

describe("apiRequest 401 handling", () => {
  it("refreshes once and retries the request with the new token", async () => {
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: "expired" }))
      .mockResolvedValueOnce(json(200, { access_token: "new-access", refresh_token: "new-refresh" }))
      .mockResolvedValueOnce(json(200, { ok: true }));

    const result = await apiRequest("/api/v1/projects");

    expect(result).toEqual({ ok: true });
    expect(callsTo("/api/v1/auth/refresh")).toHaveLength(1);

    const retry = fetchMock.mock.calls[2][1];
    expect(retry.headers.Authorization).toBe("Bearer new-access");
    expect(getAccessToken()).toBe("new-access");
    expect(getRefreshToken()).toBe("new-refresh");
    expect(expired).not.toHaveBeenCalled();
  });

  it("parallel 401s share ONE refresh call (single-flight)", async () => {
    let refreshCalls = 0;

    fetchMock.mockImplementation(async (url, options) => {
      if (url.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return json(200, { access_token: "new-access", refresh_token: "new-refresh" });
      }

      return options.headers.Authorization === "Bearer new-access"
        ? json(200, { ok: url })
        : json(401, { detail: "expired" });
    });

    const results = await Promise.all([
      apiRequest("/api/v1/projects"),
      apiRequest("/api/v1/dashboard/summary"),
      apiRequest("/api/v1/reports"),
    ]);

    expect(refreshCalls).toBe(1);
    // Independent of VITE_API_BASE_URL: compare only the path.
    expect(results.map((r) => r.ok.replace(/^.*?(?=\/api\/)/, ""))).toEqual([
      "/api/v1/projects",
      "/api/v1/dashboard/summary",
      "/api/v1/reports",
    ]);
  });

  it("a request that finds a newer token already stored retries without refreshing", async () => {
    fetchMock.mockImplementationOnce(async () => {
      // Another request rotated the tokens while this one was in flight.
      setTokens({ access_token: "rotated", refresh_token: "rotated-r" });
      return json(401, { detail: "expired" });
    });
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }));

    await apiRequest("/api/v1/projects");

    expect(callsTo("/api/v1/auth/refresh")).toHaveLength(0);
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer rotated");
  });

  it("does not loop: a second 401 after the retry ends the session", async () => {
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: "expired" }))
      .mockResolvedValueOnce(json(200, { access_token: "n", refresh_token: "nr" }))
      .mockResolvedValueOnce(json(401, { detail: "still no" }));

    await expect(apiRequest("/api/v1/projects")).rejects.toMatchObject({ status: 401 });

    expect(fetchMock).toHaveBeenCalledTimes(3); // request, refresh, ONE retry
    expect(expired).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });

  it("failed refresh clears tokens and signals session expiry", async () => {
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: "expired" }))
      .mockResolvedValueOnce(json(401, { detail: "Your session has expired. Please sign in again." }));

    await expect(apiRequest("/api/v1/projects")).rejects.toMatchObject({ status: 401 });

    expect(expired).toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2); // no retry after failed refresh
  });

  it("a network failure during refresh keeps the session", async () => {
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: "expired" }))
      .mockRejectedValueOnce(new TypeError("offline"));

    await expect(apiRequest("/api/v1/projects")).rejects.toThrow(/Unable to connect/);

    expect(expired).not.toHaveBeenCalled();
    expect(getRefreshToken()).toBe("old-refresh");
  });

  it.each([
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/oauth/exchange",
  ])("never tries to refresh for %s", async (path) => {
    fetchMock.mockResolvedValue(json(401, { detail: "Invalid email or password." }));

    await expect(apiRequest(path, { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 401,
      message: "Invalid email or password.",
    });

    expect(callsTo("/api/v1/auth/refresh")).toHaveLength(0);
  });

  it("does not refresh when there was no session to begin with", async () => {
    localStorage.clear();
    fetchMock.mockResolvedValue(json(401, { detail: "no" }));

    await expect(apiRequest("/api/v1/projects")).rejects.toMatchObject({ status: 401 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("apiRequest error parsing", () => {
  it("exposes the error code from an object detail", async () => {
    fetchMock.mockResolvedValue(
      json(403, { detail: { code: "email_not_confirmed", message: "Please confirm your email." } })
    );

    await expect(
      apiRequest("/api/v1/auth/login", { method: "POST", body: "{}" })
    ).rejects.toMatchObject({ status: 403, code: "email_not_confirmed", message: "Please confirm your email." });
  });

  it("exposes Retry-After on 429", async () => {
    fetchMock.mockResolvedValue(json(429, { detail: "Too many attempts." }, { "Retry-After": "42" }));

    await expect(apiRequest("/api/v1/auth/forgot-password", { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 429,
      retryAfter: 42,
    });
  });

  it("joins FastAPI validation messages", async () => {
    fetchMock.mockResolvedValue(json(422, { detail: [{ msg: "A" }, { msg: "B" }] }));

    await expect(apiRequest("/api/v1/auth/signup", { method: "POST", body: "{}" })).rejects.toThrow("A, B");
  });
});
