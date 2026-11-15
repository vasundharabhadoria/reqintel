import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { readFileSync } from "node:fs";

vi.mock("../../../api/authApi", () => ({ getOAuthUrl: vi.fn() }));

import { getOAuthUrl } from "../../../api/authApi";
import OAuthButtons from "./OAuthButtons";

beforeEach(() => vi.resetAllMocks());

describe("OAuthButtons", () => {
  it("renders Google and GitHub as ENABLED buttons by default", () => {
    render(<OAuthButtons />);

    for (const name of [/Continue with Google/, /Continue with GitHub/]) {
      const button = screen.getByRole("button", { name });

      expect(button).toBeEnabled();
      expect(button).not.toHaveAttribute("disabled");
    }
  });

  it("a click really starts the flow for THAT provider", async () => {
    getOAuthUrl.mockReturnValue(new Promise(() => {})); // stays pending
    const user = userEvent.setup();
    render(<OAuthButtons />);

    await user.click(screen.getByRole("button", { name: /Continue with GitHub/ }));

    expect(getOAuthUrl).toHaveBeenCalledTimes(1);
    expect(getOAuthUrl.mock.calls[0][0]).toBe("github");
    expect(await screen.findByText("Redirecting...")).toBeInTheDocument();
  });

  it("a provider that is switched off shows the backend's clear message and re-enables the buttons", async () => {
    getOAuthUrl.mockRejectedValue(
      Object.assign(new Error("Sign-in with Google is not enabled for this application yet."), { status: 503 })
    );
    const onError = vi.fn();
    const user = userEvent.setup();
    render(<OAuthButtons onError={onError} />);

    await user.click(screen.getByRole("button", { name: /Continue with Google/ }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringContaining("not enabled")));
    expect(screen.getByRole("button", { name: /Continue with Google/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Continue with GitHub/ })).toBeEnabled();
  });

  it("Back from the provider (bfcache restore) does not leave the buttons stuck on 'Redirecting...'", async () => {
    getOAuthUrl.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    render(<OAuthButtons />);

    await user.click(screen.getByRole("button", { name: /Continue with Google/ }));
    expect(screen.getByText("Redirecting...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue with GitHub/ })).toBeDisabled();

    act(() => {
      const event = new Event("pageshow");
      event.persisted = true;
      window.dispatchEvent(event);
    });

    expect(screen.queryByText("Redirecting...")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue with GitHub/ })).toBeEnabled();
  });

  it("a normal (non-cached) pageshow does not reset an in-progress redirect", async () => {
    getOAuthUrl.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    render(<OAuthButtons />);

    await user.click(screen.getByRole("button", { name: /Continue with Google/ }));

    act(() => {
      const event = new Event("pageshow");
      event.persisted = false;
      window.dispatchEvent(event);
    });

    expect(screen.getByText("Redirecting...")).toBeInTheDocument();
  });

  it("can be disabled by the parent while the password form is submitting", () => {
    render(<OAuthButtons disabled />);
    expect(screen.getByRole("button", { name: /Continue with Google/ })).toBeDisabled();
  });
});

// Read from disk: the test config turns CSS processing off, so a `?raw`
// import would be empty.
// (Vitest runs from the frontend folder.)
const authCss = readFileSync("src/features/auth/styles/auth.css", "utf8");

describe("auth.css regression: buttons must not LOOK disabled when they are enabled", () => {
  // Root cause of the red prohibited cursor: a leftover 'coming soon' rule
  // gave the base class cursor:not-allowed + opacity:0.7 in every state.
  const baseRule = authCss.match(/\.auth-oauth-button\s*\{([^}]*)\}/)?.[1] ?? "";

  it("the base rule uses a pointer cursor and full opacity", () => {
    expect(baseRule).not.toBe("");
    expect(baseRule).toMatch(/cursor:\s*pointer/);
    expect(baseRule).not.toMatch(/not-allowed/);
    expect(baseRule).not.toMatch(/opacity/);
  });

  it("not-allowed is applied only to the :disabled state", () => {
    expect(authCss).toMatch(/\.auth-oauth-button:disabled\s*\{[^}]*not-allowed/);
  });
});
