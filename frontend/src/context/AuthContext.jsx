import { useEffect, useState } from "react";

import {
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from "../api/authApi";
import { clearTokens, getAccessToken, setTokens } from "../api/tokenStorage";
import { AuthContext } from "./AuthContextObject";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function restoreSession() {
      const token = getAccessToken();

      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const currentUser = await getCurrentUser();
        setUser(currentUser);
      } catch {
        clearTokens();
        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    restoreSession();
  }, []);

  async function login(email, password) {
    const tokens = await loginUser(email, password);

    setTokens(tokens);

    const currentUser = await getCurrentUser();
    setUser(currentUser);

    return currentUser;
  }

  async function register(fullName, email, password) {
    return await registerUser(fullName, email, password);
  }

  async function logout() {
    try {
      await logoutUser();
    } catch {
      // Token may already be expired/invalid - clear local state regardless.
    }

    clearTokens();
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}