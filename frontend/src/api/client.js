import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./tokenStorage";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Fired when the session can no longer be recovered (refresh failed). The
// AuthProvider listens for it, clears its state and ProtectedRoute redirects
// to /login.
export const SESSION_EXPIRED_EVENT = "reqintel:session-expired";

// Requests that must never trigger a refresh: they either have no session yet
// or ARE the refresh, so retrying would loop.
const NO_REFRESH_PREFIXES = [
  "/api/v1/auth/login",
  "/api/v1/auth/signup",
  "/api/v1/auth/refresh",
  "/api/v1/auth/forgot-password",
  "/api/v1/auth/reset-password",
  "/api/v1/auth/resend-confirmation",
  "/api/v1/auth/oauth/",
];

function allowsRefresh(endpoint) {
  return !NO_REFRESH_PREFIXES.some((prefix) => endpoint.startsWith(prefix));
}

function buildError(response, data) {
  let message = "Something went wrong. Please try again.";
  let code;

  if (typeof data?.detail === "string") {
    message = data.detail;
  } else if (Array.isArray(data?.detail)) {
    message = data.detail.map((error) => error.msg).join(", ");
  } else if (data?.detail && typeof data.detail === "object") {
    message = data.detail.message || message;
    code = data.detail.code;
  }

  const error = new Error(message);
  error.status = response.status;

  if (code) {
    error.code = code;
  }

  const retryAfter = Number(response.headers?.get?.("Retry-After"));

  if (retryAfter > 0) {
    error.retryAfter = retryAfter;
  }

  return error;
}

function notifySessionExpired() {
  clearTokens();
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

let refreshPromise = null;

/**
 * Exchange the refresh token for a new pair. Single-flight: every request
 * that hits a 401 at the same time awaits the SAME call. Supabase rotates
 * refresh tokens, so two parallel refreshes with one token would make the
 * second fail and wrongly log the user out.
 */
export function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = getRefreshToken();

      if (!refreshToken) {
        throw Object.assign(new Error("No refresh token."), { status: 401 });
      }

      let response;

      try {
        response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      } catch {
        // Offline / server down: keep the session so a retry can succeed.
        throw new Error("Unable to connect to the server.");
      }

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const error = buildError(response, data);

        // The refresh token itself was rejected: the session is over.
        if (response.status === 401 || response.status === 403) {
          notifySessionExpired();
        }

        throw error;
      }

      // No `remember` option: the pair stays in the storage already in use.
      setTokens(data);
      return data.access_token;
    })().finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}

async function send(endpoint, options, token) {
  const isFormData = options.body instanceof FormData;

  try {
    return await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error("Unable to connect to the server.");
  }
}

export async function apiRequest(endpoint, options = {}) {
  const expectBlob = options.responseType === "blob";
  const tokenUsed = getAccessToken();

  let response = await send(endpoint, options, tokenUsed);

  if (response.status === 401 && tokenUsed && allowsRefresh(endpoint)) {
    // Another request may already have refreshed while this one was in
    // flight; in that case just retry with the newer token.
    let freshToken = getAccessToken();

    if (!freshToken || freshToken === tokenUsed) {
      try {
        freshToken = await refreshSession();
      } catch (refreshError) {
        // Network/server trouble during refresh: report that, not "401".
        if (refreshError.status !== 401 && refreshError.status !== 403) {
          throw refreshError;
        }

        freshToken = null;
      }
    }

    if (freshToken) {
      // Exactly one retry; its result is returned as-is (no loop).
      response = await send(endpoint, options, freshToken);
    }

    if (response.status === 401) {
      notifySessionExpired();
    }
  }

  if (expectBlob) {
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw buildError(response, data);
    }

    return await response.blob();
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw buildError(response, data);
  }

  return data;
}
