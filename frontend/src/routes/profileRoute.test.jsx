import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../api/profileApi", () => ({
  getProfile: vi.fn().mockResolvedValue({
    id: "1", email: "a@b.com", full_name: "Asha Verma", role: "business_analyst",
    is_active: true, created_at: "2026-03-14T10:00:00Z", last_login_at: null,
    auth_provider: "email", providers: ["email"], reauth_method: "password",
  }),
  updateProfile: vi.fn(),
  deleteAccount: vi.fn(),
}));

import { AuthContext } from "../context/AuthContextObject";
import AppRoutes from "./AppRoutes";

function renderAt(route, auth) {
  return render(
    <AuthContext.Provider
      value={{ user: null, loading: false, isAuthenticated: false, logout: async () => {}, endSession() {}, ...auth }}
    >
      <MemoryRouter initialEntries={[route]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe("/profile route", () => {
  it("is protected: anonymous visitors are sent to the login page", () => {
    renderAt("/profile", {});

    expect(screen.getByText("Welcome Back!")).toBeInTheDocument();
    expect(screen.queryByText("Personal information")).not.toBeInTheDocument();
  });

  it("renders for a signed-in user", async () => {
    renderAt("/profile", {
      user: { id: "1", email: "a@b.com", role: "business_analyst" },
      isAuthenticated: true,
    });

    expect(await screen.findByText("Personal information")).toBeInTheDocument();
    expect(screen.getByText("Danger Zone")).toBeInTheDocument();
  });

  it("shows a loading state (no flash of login) while the session restores", () => {
    renderAt("/profile", { loading: true });

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("Welcome Back!")).not.toBeInTheDocument();
  });
});
