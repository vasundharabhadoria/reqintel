import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { saveOAuthFlow } from "../features/auth/pkce";
import OAuthReturnGate from "./OAuthReturnGate";
import { returnTarget } from "./returnTarget";

const at = (pathname, search = "", hash = "") => returnTarget({ pathname, search, hash });

describe("returnTarget (where a return from Supabase is handled)", () => {
  it("forwards a recovery link that landed on the Site URL to /reset-password", () => {
    expect(at("/", "", "#access_token=abc&type=recovery")).toBe(
      "/reset-password#access_token=abc&type=recovery"
    );
  });

  it("forwards email-confirmation and fragment errors to the callback page", () => {
    expect(at("/login", "", "#access_token=a&type=signup")).toBe("/auth/callback#access_token=a&type=signup");
    expect(at("/", "", "#error=access_denied&error_code=otp_expired")).toBe(
      "/auth/callback#error=access_denied&error_code=otp_expired"
    );
  });

  it("forwards an OAuth code ONLY when this browser started the flow", () => {
    expect(at("/", "?code=abc")).toBeNull(); // stray code: not ours

    saveOAuthFlow({ verifier: "v".repeat(64), remember: false, provider: "google" });

    expect(at("/", "?code=abc")).toBe("/auth/callback?code=abc");
    expect(at("/login", "?error=access_denied")).toBe("/auth/callback?error=access_denied");
  });

  it("never redirects from the pages that already handle it (no loops)", () => {
    saveOAuthFlow({ verifier: "v".repeat(64), remember: false, provider: "google" });

    expect(at("/auth/callback", "?code=abc")).toBeNull();
    expect(at("/reset-password", "", "#access_token=a&type=recovery")).toBeNull();
  });

  it("ignores ordinary navigation", () => {
    expect(at("/dashboard")).toBeNull();
    expect(at("/login", "?foo=bar", "#section")).toBeNull();
  });
});

describe("OAuthReturnGate", () => {
  function renderAt(url) {
    return render(
      <MemoryRouter initialEntries={[url]}>
        <OAuthReturnGate>
          <Routes>
            <Route path="/" element={<p>HOME</p>} />
            <Route path="/auth/callback" element={<p>CALLBACK PAGE</p>} />
            <Route path="/reset-password" element={<p>RESET PAGE</p>} />
          </Routes>
        </OAuthReturnGate>
      </MemoryRouter>
    );
  }

  it("rescues an OAuth return that landed on '/' (redirect URL missing from Supabase allow-list)", () => {
    saveOAuthFlow({ verifier: "v".repeat(64), remember: true, provider: "github" });
    renderAt("/?code=abc");
    expect(screen.getByText("CALLBACK PAGE")).toBeInTheDocument();
  });

  it("rescues a password-recovery link that landed on '/'", () => {
    renderAt("/#access_token=abc&type=recovery");
    expect(screen.getByText("RESET PAGE")).toBeInTheDocument();
  });

  it("leaves normal pages alone", () => {
    renderAt("/");
    expect(screen.getByText("HOME")).toBeInTheDocument();
  });
});
