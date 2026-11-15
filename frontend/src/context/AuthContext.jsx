import { useCallback, useEffect, useState } from "react";

import {
  exchangeOAuthCode,
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from "../api/authApi";
import { SESSION_EXPIRED_EVENT } from "../api/client";
import {
  TOKEN_STORAGE_KEYS,
  clearTokens,
  getAccessToken,
  setTokens,
} from "../api/tokenStorage";
import { AuthContext } from "./AuthContextObject";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function restoreSession() {
      if (!getAccessToken()) {
        setLoading(false);
        return;
      }

      try {
        // apiRequest refreshes an expired access token and retries once.
        setUser(await getCurrentUser());
      } catch (err) {
        // 401/403 means the session is gone. A network or server error keeps
        // the stored tokens so a reload can retry.
        if (err.status === 401 || err.status === 403) {
          clearTokens();
        }

        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    restoreSession();
  }, []);

  // The session can no longer be refreshed -> drop local state; the
  // ProtectedRoute then redirects to /login.
  useEffect(() => {
    function handleExpired() {
      clearTokens();
      setUser(null);
    }

    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired);

    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired);
  }, []);

  // Cross-tab: logging out (or in) in another tab is reflected here. The
  // `storage` event only fires for localStorage, i.e. "Remember me" sessions;
  // a session-only login is per tab by design.
  useEffect(() => {
    function handleStorage(event) {
      const isTokenKey =
        event.key === null || event.key === TOKEN_STORAGE_KEYS.access;

      if (!isTokenKey) {
        return;
      }

      if (!getAccessToken()) {
        setUser(null);
        return;
      }

      getCurrentUser()
        .then(setUser)
        .catch(() => setUser(null));
    }

    window.addEventListener("storage", handleStorage);

    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const completeLogin = useCallback(async (tokens, remember) => {
    setTokens(tokens, { remember });

    try {
      const currentUser = await getCurrentUser();

      setUser(currentUser);

      return currentUser;
    } catch (err) {
      // e.g. 403 account_disabled: never leave half a session behind.
      clearTokens();
      setUser(null);

      throw err;
    }
  }, []);

  const login = useCallback(
    async (email, password, remember = false) => {
      const tokens = await loginUser(email, password);

      return completeLogin(tokens, remember);
    },
    [completeLogin]
  );

  const loginWithOAuthCode = useCallback(
    async (code, codeVerifier, remember = false) => {
      const tokens = await exchangeOAuthCode(code, codeVerifier);

      return completeLogin(tokens, remember);
    },
    [completeLogin]
  );

  const register = useCallback(
    (fullName, email, password) => registerUser(fullName, email, password),
    []
  );

  const logout = useCallback(async () => {
    try {
      await logoutUser();
    } catch {
      // Token may already be expired/invalid - clear local state regardless.
    }

    clearTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        login,
        loginWithOAuthCode,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
