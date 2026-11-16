import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithAuth } from "../../../test/renderWithAuth";
import { clearProfileSummary } from "../../../hooks/useProfileSummary";
import SettingsPage from "./SettingsPage";

vi.mock("../../../api/profileApi", () => ({ getProfile: vi.fn() }));
vi.mock("../../../api/authApi", () => ({ forgotPassword: vi.fn() }));

import { forgotPassword } from "../../../api/authApi";
import { getProfile } from "../../../api/profileApi";

const user = { id: "1", email: "asha@example.com", role: "business_analyst" };

function renderPage(auth = {}) {
  return renderWithAuth(<SettingsPage />, {
    auth: { user, isAuthenticated: true, ...auth },
    route: "/settings",
    path: "/settings",
    extraRoutes: [<Route key="l" path="/login" element={<p>LOGIN ROUTE</p>} />],
  });
}

beforeEach(() => {
  clearProfileSummary();
  vi.clearAllMocks();
  getProfile.mockResolvedValue({
    id: "1",
    full_name: "Asha Verma",
    auth_provider: "email",
    reauth_method: "password",
  });
});

describe("SettingsPage", () => {
  it("shows account details from the real profile", async () => {
    renderPage();

    expect(await screen.findAllByText("Asha Verma")).not.toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
  });

  it("sends a password reset email for password accounts", async () => {
    forgotPassword.mockResolvedValue({ message: "Reset link sent." });
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: /password reset link/i })
    );

    expect(forgotPassword).toHaveBeenCalledWith("asha@example.com");
    expect(await screen.findByText("Reset link sent.")).toBeInTheDocument();
  });

  it("does not offer password reset for OAuth accounts", async () => {
    getProfile.mockResolvedValue({
      id: "1",
      full_name: "Asha Verma",
      auth_provider: "google",
      reauth_method: "recent_login",
    });
    renderPage();

    expect(await screen.findByText(/managed by Google/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /password reset link/i })).toBeNull();
  });

  it("signs out and redirects to /login", async () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    renderPage({ logout });

    await userEvent.click(await screen.findByRole("button", { name: "Sign Out" }));

    await waitFor(() => expect(screen.getByText("LOGIN ROUTE")).toBeInTheDocument());
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
