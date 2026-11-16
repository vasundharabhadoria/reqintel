import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { renderWithAuth } from "../../test/renderWithAuth";
import AppShell from "./AppShell";

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
        <Route key="l" path="/login" element={<p>LOGIN ROUTE</p>} />,
      ],
    }
  );
}

describe("AppShell profile menu", () => {
  it("shows the signed-in user's real role, not a hard-coded one", () => {
    renderShell({ user: { ...user, role: "admin" } });

    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.queryByText("Business Analyst")).not.toBeInTheDocument();
  });

  it("opens My Profile from the avatar menu", async () => {
    const u = userEvent.setup();
    renderShell();

    await u.click(screen.getByRole("button", { name: /Business Analyst/ }));
    await u.click(await screen.findByRole("menuitem", { name: /My Profile/ }));

    expect(await screen.findByText("PROFILE ROUTE")).toBeInTheDocument();
  });

  it("the sidebar Settings entry opens the profile page", async () => {
    renderShell();

    await userEvent.click(screen.getByRole("button", { name: /Settings/ }));

    expect(await screen.findByText("PROFILE ROUTE")).toBeInTheDocument();
  });

  it("logs out from the menu and goes to /login", async () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    const u = userEvent.setup();
    renderShell({ logout });

    await u.click(screen.getByRole("button", { name: /Business Analyst/ }));
    await u.click(await screen.findByRole("menuitem", { name: /Logout/ }));

    await waitFor(() => expect(screen.getByText("LOGIN ROUTE")).toBeInTheDocument());
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
