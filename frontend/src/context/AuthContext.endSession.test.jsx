import { useEffect } from "react";
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/authApi", () => ({
  loginUser: vi.fn(),
  registerUser: vi.fn(),
  exchangeOAuthCode: vi.fn(),
  getCurrentUser: vi.fn(),
  logoutUser: vi.fn(),
}));

import * as authApi from "../api/authApi";
import { getAccessToken, getRefreshToken, setTokens } from "../api/tokenStorage";
import { useAuth } from "../hooks/useAuth";
import { AuthProvider } from "./AuthContext";

const holder = { current: null };

function Probe() {
  const auth = useAuth();
  useEffect(() => {
    holder.current = auth;
  });
  return <p>{auth.loading ? "loading" : auth.user ? `user:${auth.user.email}` : "anonymous"}</p>;
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe("AuthProvider.endSession (after account deletion)", () => {
  for (const remember of [true, false]) {
    it(`clears tokens and user for a ${remember ? "persistent" : "session-only"} login`, async () => {
      setTokens({ access_token: "a", refresh_token: "r" }, { remember });
      authApi.getCurrentUser.mockResolvedValue({ id: "1", email: "a@b.com", role: "business_analyst" });

      render(<AuthProvider><Probe /></AuthProvider>);
      expect(await screen.findByText("user:a@b.com")).toBeInTheDocument();

      act(() => holder.current.endSession());

      expect(await screen.findByText("anonymous")).toBeInTheDocument();
      expect(getAccessToken()).toBeNull();
      expect(getRefreshToken()).toBeNull();
      expect(localStorage.length).toBe(0);
      expect(sessionStorage.length).toBe(0);
      // the server session is gone with the account: no logout call is made
      expect(authApi.logoutUser).not.toHaveBeenCalled();
    });
  }
});
