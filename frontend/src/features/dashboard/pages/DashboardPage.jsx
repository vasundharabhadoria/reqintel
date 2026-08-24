import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ClipboardList, Plus, Sparkles } from "lucide-react";

import AppShell from "../../../components/layout/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import { useToast } from "../../../hooks/useToast";
import { createProject, listProjects } from "../../../api/projectApi";
import ProjectFormModal from "../../projects/components/ProjectFormModal";
import StatusBadge from "../../projects/components/StatusBadge";
import "../styles/dashboard.css";

function formatDate(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}

function DashboardPage() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { showToast } = useToast();

  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const handleSessionExpired = useCallback(async () => {
    showToast("Your session has expired. Please log in again.", "error");
    await logout();
    navigate("/login");
  }, [logout, navigate, showToast]);

  const fetchDashboardProjects = useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
      const response = await listProjects({});
      setProjects(response.items);
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }
      setLoadError(err.message || "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, [handleSessionExpired]);

  useEffect(() => {
    fetchDashboardProjects();
  }, [fetchDashboardProjects]);

  const activeProjectCount = projects.filter((project) => project.status === "active").length;
  const recentProjects = projects.slice(0, 3);

  async function handleCreateSubmit(values) {
    await createProject(values);
    showToast("Project created successfully.");
    setCreateOpen(false);
    await fetchDashboardProjects();
  }

  return (
    <AppShell active="dashboard">
      <div className="dashboard-layout">
        <div className="dashboard-main">
          <h1>Welcome, Business Analyst</h1>

          <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={16} /> Create New Project
          </button>

          <section className="dashboard-section">
            <h2>Recent Projects</h2>

            {loading && <p className="muted-text">Loading projects...</p>}

            {!loading && loadError && (
              <div className="table-state table-state-error">
                <p>{loadError}</p>
                <button type="button" className="btn btn-secondary" onClick={fetchDashboardProjects}>
                  Try Again
                </button>
              </div>
            )}

            {!loading && !loadError && recentProjects.length === 0 && (
              <p className="muted-text">No projects yet. Create your first project to get started.</p>
            )}

            {!loading && !loadError && recentProjects.length > 0 && (
              <div className="recent-projects-grid">
                {recentProjects.map((project) => (
                  <button
                    type="button"
                    key={project.id}
                    className="recent-project-card"
                    onClick={() => navigate(`/projects/${project.id}`)}
                  >
                    <div className="recent-project-card-top">
                      <StatusBadge status={project.status} />
                    </div>
                    <p className="recent-project-name">{project.name}</p>
                    <p className="recent-project-date">Dated · {formatDate(project.created_at)}</p>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="dashboard-section">
            <h2>Recent Activity</h2>
            <div className="placeholder-card">
              <ClipboardList size={20} />
              <div>
                <p className="placeholder-title">Coming soon</p>
                <p className="placeholder-text">Activity history isn't exposed by the API yet.</p>
              </div>
            </div>
          </section>
        </div>

        <aside className="dashboard-sidebar">
          <h2 className="dashboard-stats-heading">Workspace Statistics</h2>

          <div className="stats-grid">
            <div className="stat-card">
              <p className="stat-label">Projects</p>
              <p className="stat-value">{loading ? "—" : projects.length}</p>
              <p className="stat-caption">{loading ? "" : `${activeProjectCount} Active`}</p>
            </div>

            <div className="stat-card stat-card-disabled">
              <p className="stat-label">Requirements</p>
              <p className="stat-value">—</p>
              <p className="stat-caption">Coming soon</p>
            </div>

            <div className="stat-card stat-card-disabled">
              <p className="stat-label">Pending Reviews</p>
              <p className="stat-value">—</p>
              <p className="stat-caption">Coming soon</p>
            </div>

            <div className="stat-card stat-card-disabled">
              <p className="stat-label">Overall Quality</p>
              <p className="stat-value">—</p>
              <p className="stat-caption">Coming soon</p>
            </div>
          </div>

          <div className="ai-suggestions-card">
            <div className="ai-suggestions-header">
              <Sparkles size={16} />
              <span>AI Suggestions Generated</span>
            </div>
            <p className="stat-value">—</p>
            <p className="placeholder-text">This module isn't implemented yet.</p>
          </div>
        </aside>
      </div>

      <ProjectFormModal
        open={createOpen}
        mode="create"
        initialProject={null}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreateSubmit}
        onAuthError={handleSessionExpired}
      />
    </AppShell>
  );
}

export default DashboardPage;