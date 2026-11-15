import { Navigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { homePathForUser } from "./homePath";

function RootRedirect() {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return <p className="auth-route-loading">Loading...</p>;
  }

  return (
    <Navigate to={isAuthenticated ? homePathForUser(user) : "/login"} replace />
  );
}

export default RootRedirect;
