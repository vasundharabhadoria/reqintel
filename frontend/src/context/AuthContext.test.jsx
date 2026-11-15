import { useEffect } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/authApi", () => ({
  loginUser: vi.fn(),
  registerUser: vi.fn(),
  exchangeOAuthCode: vi.fn(),
  getCurrentUser: vi.fn(),
  logoutUser: vi.fn(),
}));

import * as authApi from "../api/authApi";
import { SESSION_EXPIRED_EVENT } from "../api/client";
import { getAccessToken, setTokens } from "../api/tokenStorage";
import { useAuth } from "../hooks/useAuth";
import { AuthProvider } from "./AuthContext";

// Holds the latest auth value so tests can call login()/logout() directly.
const holder = { current: null };

function Probe() {
  const auth = useAuth();

  useEffect(() => {
    holder.current = auth;
  });

  return <p>{auth.loading ? "loading" : auth.user ? `user:${auth.user.email}` : "anonymous"}</p>;
}

const me = { id: "1", email: "a@b.com", role: "business_analyst" };

beforeEach(() => {
  vi.resetAllMocks();
});

const mount = () => render(<AuthProvider><Probe /></AuthProvider>);

describe("AuthProvider", () => {
  it("restores the session after a page refresh", async () => {
    setTokens({ access_token: "a", refresh_token: "r" }, { remember: true });
    authApi.getCurrentUser.mockResolvedValue(me);

    mount();

    expect(await screen.findByText("user:a@b.com")).toBeInTheDocument();
  });

  it("is anonymous without tokens and never calls the API", async () => {
    mount();

    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    expect(authApi.getCurrentUser).not.toHaveBeenCalled();
  });

  it("drops stored tokens when the session is no longer valid", async () => {
    setTokens({ access_token: "a", refresh_token: "r" }, { remember: true });
    authApi.getCurrentUser.mockRejectedValue(Object.assign(new Error("x"), { status: 401 }));

    mount();

    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
  });

  it("keeps stored tokens on a network error so a reload can retry", async () => {
    setTokens({ access_token: "a", refresh_token: "r" }, { remember: true });
    authApi.getCurrentUser.mockRejectedValue(new Error("Unable to connect to the server."));

    mount();

    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    expect(getAccessToken()).toBe("a");
  });

  it("login stores tokens per Remember me and loads the user", async () => {
    authApi.loginUser.mockResolvedValue({ access_token: "a", refresh_token: "r" });
    authApi.getCurrentUser.mockResolvedValue(me);
    mount();
    await screen.findByText("anonymous");

    await act(() => holder.current.login("a@b.com", "pw", false));

    expect(sessionStorage.getItem("access_token")).toBe("a");
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(await screen.findByText("user:a@b.com")).toBeInTheDocument();
  });

  it("login with Remember me persists across browser restarts", async () => {
    authApi.loginUser.mockResolvedValue({ access_token: "a", refresh_token: "r" });
    authApi.getCurrentUser.mockResolvedValue(me);
    mount();
    await screen.findByText("anonymous");

    await act(() => holder.current.login("a@b.com", "pw", true));

    expect(localStorage.getItem("refresh_token")).toBe("r");
  });

  it("a deactivated account leaves no half-session behind", async () => {
    authApi.loginUser.mockResolvedValue({ access_token: "a", refresh_token: "r" });
    authApi.getCurrentUser.mockRejectedValue(
      Object.assign(new Error("This account has been deactivated."), { status: 403 })
    );
    mount();
    await screen.findByText("anonymous");

    await expect(act(() => holder.current.login("a@b.com", "pw", true))).rejects.toThrow(/deactivated/);

    expect(getAccessToken()).toBeNull();
    expect(screen.getByText("anonymous")).toBeInTheDocument();
  });

  it("logout clears tokens and state even if the server call fails", async () => {
    setTokens({ access_token: "a", refresh_token: "r" }, { remember: true });
    authApi.getCurrentUser.mockResolvedValue(me);
    authApi.logoutUser.mockRejectedValue(new Error("expired"));
    mount();
    await screen.findByText("user:a@b.com");

    await act(() => holder.current.logout());

    expect(getAccessToken()).toBeNull();
    expect(screen.getByText("anonymous")).toBeInTheDocument();
  });

  it("session-expired event signs the user out", async () => {
    setTokens({ access_token: "a", refresh_token: "r" }, { remember: true });
    authApi.getCurrentUser.mockResolvedValue(me);
    mount();
    await screen.findByText("user:a@b.com");

    act(() => window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT)));

    await waitFor(() => expect(screen.getByText("anonymous")).toBeInTheDocument());
    expect(getAccessToken()).toBeNull();
  });

  it("logging out in another tab signs this tab out", async () => {
    setTokens({ access_token: "a", refresh_token: "r" }, { remember: true });
    authApi.getCurrentUser.mockResolvedValue(me);
    mount();
    await screen.findByText("user:a@b.com");

    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: "access_token", newValue: null })));

    await waitFor(() => expect(screen.getByText("anonymous")).toBeInTheDocument());
  });

  it("OAuth code login uses the stored remember choice", async () => {
    authApi.exchangeOAuthCode.mockResolvedValue({ access_token: "oa", refresh_token: "or" });
    authApi.getCurrentUser.mockResolvedValue(me);
    mount();
    await screen.findByText("anonymous");

    await act(() => holder.current.loginWithOAuthCode("code123", "verifier", true));

    expect(authApi.exchangeOAuthCode).toHaveBeenCalledWith("code123", "verifier");
    expect(localStorage.getItem("access_token")).toBe("oa");
  });
});
