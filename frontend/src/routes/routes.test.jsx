import { screen } from "@testing-library/react";
import { Route } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { renderWithAuth } from "../test/renderWithAuth";
import ProtectedRoute from "./ProtectedRoute";
import PublicOnlyRoute from "./PublicOnlyRoute";
import RootRedirect from "./RootRedirect";

const analyst = { id: "1", email: "a@b.com", role: "business_analyst" };
const admin = { ...analyst, role: "admin" };

const targets = [
  <Route key="login" path="/login" element={<p>LOGIN PAGE</p>} />,
  <Route key="dash" path="/dashboard" element={<p>DASHBOARD PAGE</p>} />,
  <Route key="master" path="/master-module" element={<p>MASTER PAGE</p>} />,
];

describe("ProtectedRoute", () => {
  it("redirects anonymous users to /login", () => {
    renderWithAuth(
      <ProtectedRoute><p>SECRET</p></ProtectedRoute>,
      { route: "/projects", path: "/projects", extraRoutes: targets }
    );

    expect(screen.getByText("LOGIN PAGE")).toBeInTheDocument();
    expect(screen.queryByText("SECRET")).not.toBeInTheDocument();
  });

  it("shows a loading state (no flash of login) while the session restores", () => {
    renderWithAuth(
      <ProtectedRoute><p>SECRET</p></ProtectedRoute>,
      { auth: { loading: true }, route: "/projects", path: "/projects", extraRoutes: targets }
    );

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("LOGIN PAGE")).not.toBeInTheDocument();
  });

  it("renders the page for signed-in users", () => {
    renderWithAuth(
      <ProtectedRoute><p>SECRET</p></ProtectedRoute>,
      { auth: { user: analyst, isAuthenticated: true }, route: "/projects", path: "/projects" }
    );

    expect(screen.getByText("SECRET")).toBeInTheDocument();
  });

  it("locks the page again once the session is dropped (logout / expiry)", () => {
    const { unmount } = renderWithAuth(
      <ProtectedRoute><p>SECRET</p></ProtectedRoute>,
      { auth: { user: analyst, isAuthenticated: true }, route: "/projects", path: "/projects" }
    );
    unmount();

    renderWithAuth(
      <ProtectedRoute><p>SECRET</p></ProtectedRoute>,
      { auth: { user: null, isAuthenticated: false }, route: "/projects", path: "/projects", extraRoutes: targets }
    );

    expect(screen.queryByText("SECRET")).not.toBeInTheDocument();
    expect(screen.getByText("LOGIN PAGE")).toBeInTheDocument();
  });
});

describe("PublicOnlyRoute", () => {
  it("shows login to anonymous users", () => {
    renderWithAuth(<PublicOnlyRoute><p>LOGIN FORM</p></PublicOnlyRoute>, { route: "/login", path: "/login" });
    expect(screen.getByText("LOGIN FORM")).toBeInTheDocument();
  });

  it("sends signed-in analysts to the dashboard", () => {
    renderWithAuth(
      <PublicOnlyRoute><p>LOGIN FORM</p></PublicOnlyRoute>,
      { auth: { user: analyst, isAuthenticated: true }, route: "/login", path: "/login", extraRoutes: targets }
    );
    expect(screen.getByText("DASHBOARD PAGE")).toBeInTheDocument();
  });

  it("sends signed-in admins to the master module", () => {
    renderWithAuth(
      <PublicOnlyRoute><p>LOGIN FORM</p></PublicOnlyRoute>,
      { auth: { user: admin, isAuthenticated: true }, route: "/login", path: "/login", extraRoutes: targets }
    );
    expect(screen.getByText("MASTER PAGE")).toBeInTheDocument();
  });
});

describe("RootRedirect", () => {
  it("anonymous -> /login, signed in -> home", () => {
    const anon = renderWithAuth(<RootRedirect />, { route: "/", path: "/", extraRoutes: targets });
    expect(screen.getByText("LOGIN PAGE")).toBeInTheDocument();
    anon.unmount();

    renderWithAuth(<RootRedirect />, {
      auth: { user: analyst, isAuthenticated: true }, route: "/", path: "/", extraRoutes: targets,
    });
    expect(screen.getByText("DASHBOARD PAGE")).toBeInTheDocument();
  });
});
