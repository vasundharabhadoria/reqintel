import { Navigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { homePathForUser } from "./homePath";

// Login / register / forgot-password make no sense for a signed-in user.
function PublicOnlyRoute({ children }) {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return <p className="auth-route-loading">Loading...</p>;
  }

  if (isAuthenticated) {
    return <Navigate to={homePathForUser(user)} replace />;
  }

  return children;
}

export default PublicOnlyRoute;
