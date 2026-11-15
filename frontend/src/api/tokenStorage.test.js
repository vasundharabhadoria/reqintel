import { describe, expect, it } from "vitest";

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  isPersistentSession,
  setTokens,
} from "./tokenStorage";

const pair = { access_token: "a1", refresh_token: "r1" };

describe("tokenStorage / Remember me", () => {
  it("remember=true stores in localStorage only", () => {
    setTokens(pair, { remember: true });

    expect(localStorage.getItem("access_token")).toBe("a1");
    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(isPersistentSession()).toBe(true);
  });

  it("remember=false stores in sessionStorage only", () => {
    setTokens(pair, { remember: false });

    expect(sessionStorage.getItem("refresh_token")).toBe("r1");
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(isPersistentSession()).toBe(false);
  });

  it("reads find the session wherever it was stored", () => {
    setTokens(pair, { remember: true });
    expect(getAccessToken()).toBe("a1");
    expect(getRefreshToken()).toBe("r1");

    clearTokens();
    setTokens(pair, { remember: false });
    expect(getAccessToken()).toBe("a1");
  });

  it("a refresh (no remember option) keeps the storage already in use", () => {
    setTokens(pair, { remember: true });
    setTokens({ access_token: "a2", refresh_token: "r2" });

    expect(localStorage.getItem("access_token")).toBe("a2");
    expect(sessionStorage.getItem("access_token")).toBeNull();

    clearTokens();
    setTokens(pair, { remember: false });
    setTokens({ access_token: "a3", refresh_token: "r3" });

    expect(sessionStorage.getItem("access_token")).toBe("a3");
    expect(localStorage.getItem("access_token")).toBeNull();
  });

  it("a new login moves tokens and leaves no copy in the other storage", () => {
    setTokens(pair, { remember: true });
    setTokens({ access_token: "b1", refresh_token: "s1" }, { remember: false });

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("access_token")).toBe("b1");
  });

  it("clearTokens removes both storages", () => {
    setTokens(pair, { remember: true });
    sessionStorage.setItem("access_token", "stale");

    clearTokens();

    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});
