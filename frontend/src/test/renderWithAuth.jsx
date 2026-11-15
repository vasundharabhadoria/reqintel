import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthContext } from "../context/AuthContextObject";

// Renders `ui` with a stubbed auth context (no network, no providers).
export function renderWithAuth(ui, { auth = {}, route = "/", path = "*", extraRoutes = null } = {}) {
  const value = {
    user: null,
    loading: false,
    isAuthenticated: false,
    login: async () => ({ role: "business_analyst" }),
    loginWithOAuthCode: async () => ({ role: "business_analyst" }),
    register: async () => ({ message: "ok" }),
    logout: async () => {},
    ...auth,
  };

  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={ui} />
          {extraRoutes}
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}
