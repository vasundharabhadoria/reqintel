import { Navigate, Route, Routes } from "react-router-dom";

import LoginPage from "../features/auth/pages/LoginPage";
import RegisterPage from "../features/auth/pages/RegisterPage";
import DashboardPage from "../features/dashboard/pages/DashboardPage";
import ProjectsPage from "../features/projects/pages/ProjectsPage";
import ProjectWorkspacePage from "../features/requirements/pages/ProjectWorkspacePage";
import RuleEnginePage from "../features/rule-engine/pages/RuleEnginePage";
import ProtectedRoute from "./ProtectedRoute";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />

      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/projects"
        element={
          <ProtectedRoute>
            <ProjectsPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/projects/:projectId"
        element={
          <ProtectedRoute>
            <ProjectWorkspacePage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/projects/:projectId/rule-engine"
        element={
          <ProtectedRoute>
            <RuleEnginePage />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default AppRoutes;