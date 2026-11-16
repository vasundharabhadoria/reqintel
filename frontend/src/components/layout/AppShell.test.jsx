import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithAuth } from "../../test/renderWithAuth";
import { clearProfileSummary } from "../../hooks/useProfileSummary";
import AppShell from "./AppShell";

vi.mock("../../api/profileApi", () => ({
  getProfile: vi.fn(),
}));

import { getProfile } from "../../api/profileApi";

const user = { id: "1", email: "asha@example.com", role: "business_analyst" };

function renderShell(auth = {}) {
  return renderWithAuth(
    <AppShell active="dashboard">
      <p>CONTENT</p>
    </AppShell>,
    {
      auth: { user, isAuthenticated: true, ...auth },
      route: "/dashboard",
      path: "/dashboard",
      extraRoutes: [
        <Route key="p" path="/profile" element={<p>PROFILE ROUTE</p>} />,
        <Route key="s" path="/settings" element={<p>SETTINGS ROUTE</p>} />,
        <Route key="l" path="/login" element={<p>LOGIN ROUTE</p>} />,
      ],
    }
  );
}

beforeEach(() => {
  clearProfileSummary();
  getProfile.mockReset();
  getProfile.mockResolvedValue({ id: "1", full_name: "Asha Verma" });
});

describe("AppShell", () => {
  it("has no decorative bell or language selector", () => {
    renderShell();

    expect(screen.queryByRole("button", { name: /notifications/i })).toBeNull();
    expect(screen.queryByText("English")).toBeNull();
  });

  it("shows the real name and role in the sidebar profile section", async () => {
    renderShell({ user: { ...user, role: "admin" } });

    expect(await screen.findByText("Asha Verma")).toBeInTheDocument();
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.queryByText("Business Analyst")).not.toBeInTheDocument();
  });

  it("falls back to the e-mail address if the profile cannot be loaded", async () => {
    getProfile.mockRejectedValue(new Error("down"));
    renderShell();

    expect(await screen.findByText("asha@example.com")).toBeInTheDocument();
  });

  it("opens My Profile from the account menu", async () => {
    const u = userEvent.setup();
    renderShell();

    await u.click(screen.getByRole("button", { name: /Account menu/ }));
    await u.click(await screen.findByRole("menuitem", { name: /My Profile/ }));

    expect(await screen.findByText("PROFILE ROUTE")).toBeInTheDocument();
  });

  it("opens Account Settings from the account menu", async () => {
    const u = userEvent.setup();
    renderShell();

    await u.click(screen.getByRole("button", { name: /Account menu/ }));
    await u.click(await screen.findByRole("menuitem", { name: /Account Settings/ }));

    expect(await screen.findByText("SETTINGS ROUTE")).toBeInTheDocument();
  });

  it("the sidebar Settings entry opens the settings page, not the profile", async () => {
    renderShell();

    await userEvent.click(screen.getByRole("link", { name: /Settings/ }));

    expect(await screen.findByText("SETTINGS ROUTE")).toBeInTheDocument();
    expect(screen.queryByText("PROFILE ROUTE")).toBeNull();
  });

  it("signs out from the menu and goes to /login", async () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    const u = userEvent.setup();
    renderShell({ logout });

    await u.click(screen.getByRole("button", { name: /Account menu/ }));
    await u.click(await screen.findByRole("menuitem", { name: /Sign Out/ }));

    await waitFor(() => expect(screen.getByText("LOGIN ROUTE")).toBeInTheDocument());
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
