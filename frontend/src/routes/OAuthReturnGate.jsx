import { Navigate, useLocation } from "react-router-dom";

import { returnTarget } from "./returnTarget";

function OAuthReturnGate({ children }) {
  const location = useLocation();
  const target = returnTarget(location);

  if (target) {
    return <Navigate to={target} replace />;
  }

  return children;
}

export default OAuthReturnGate;
