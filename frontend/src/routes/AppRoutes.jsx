import { Navigate, Route, Routes, useParams } from "react-router-dom";

import LoginPage from "../features/auth/pages/LoginPage";
import RegisterPage from "../features/auth/pages/RegisterPage";
import ForgotPasswordPage from "../features/auth/pages/ForgotPasswordPage";
import ResetPasswordPage from "../features/auth/pages/ResetPasswordPage";
import AuthCallbackPage from "../features/auth/pages/AuthCallbackPage";
import DashboardPage from "../features/dashboard/pages/DashboardPage";
import ProjectsPage from "../features/projects/pages/ProjectsPage";
import ReportsPage from "../features/reports/pages/ReportsPage";
import ProjectWorkspacePage from "../features/requirements/pages/ProjectWorkspacePage";
import RuleEnginePage from "../features/rule-engine/pages/RuleEnginePage";
import MasterModulePage from "../features/master-module/pages/MasterModulePage";
import ProfilePage from "../features/profile/pages/ProfilePage";
import ProtectedRoute from "./ProtectedRoute";
import OAuthReturnGate from "./OAuthReturnGate";
import PublicOnlyRoute from "./PublicOnlyRoute";
import RootRedirect from "./RootRedirect";
import TraceabilityPage from "../features/requirements/pages/TraceabilityPage";
function TraceabilityRoute() {
  const { projectId } = useParams();
  return <TraceabilityPage projectId={projectId} />;
}
function AppRoutes() {
  return (
    <OAuthReturnGate>
      <Routes>
        <Route path="/" element={<RootRedirect />} />

        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              <LoginPage />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/register"
          element={
            <PublicOnlyRoute>
              <RegisterPage />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/forgot-password"
          element={
            <PublicOnlyRoute>
              <ForgotPasswordPage />
            </PublicOnlyRoute>
          }
        />

        {/* Opened from emails / OAuth redirects: must work signed in or out. */}
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />

        <Route
          path="/master-module"
          element={
            <ProtectedRoute>
              <MasterModulePage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <ProfilePage />
            </ProtectedRoute>
          }
        />

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
          path="/reports"
          element={
            <ProtectedRoute>
              <ReportsPage />
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
             <Route
    path="/projects/:projectId/traceability"
    element={
      <ProtectedRoute>
        <TraceabilityRoute />
      </ProtectedRoute>
    }
  />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </OAuthReturnGate>
  );
}

export default AppRoutes;