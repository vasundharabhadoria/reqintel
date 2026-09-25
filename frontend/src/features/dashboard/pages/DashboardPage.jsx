import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CalendarDays,
  ClipboardList,
  FileText,
  FolderKanban,
  Plus,
  Sparkles,
} from "lucide-react";

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
      setProjects(response.items || []);
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

  const activeProjectCount = projects.filter(
    (project) => project.status === "active"
  ).length;

  const recentProjects = projects.slice(0, 3);

  async function handleCreateSubmit(values) {
    try {
      await createProject(values);
      showToast("Project created successfully.");
      setCreateOpen(false);
      await fetchDashboardProjects();
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }

      showToast(err.message || "Failed to create project.", "error");
    }
  }

  return (
    <AppShell active="dashboard">
      <div className="dashboard-page">
        <div className="dashboard-content">

          {/* LEFT SIDE */}
          <main className="dashboard-main">

            {/* HEADER */}
            <div className="dashboard-header">
              <p className="dashboard-eyebrow">
                Workspace Dashboard
              </p>

              <h1>
                Welcome, Business Analyst
              </h1>

              <p className="dashboard-subtitle">
                Manage your projects, requirements and analysis in one place.
              </p>

              <button
                type="button"
                className="dashboard-create-button"
                onClick={() => setCreateOpen(true)}
              >
                <Plus size={18} />
                Create New Project
              </button>
            </div>

            {/* RECENT PROJECTS */}
            <section className="dashboard-section">
              <div className="section-heading">
                <h2>Recent Projects</h2>

                <p>
                  Your latest projects and their current status.
                </p>
              </div>

              {loading && (
                <p className="dashboard-muted">
                  Loading projects...
                </p>
              )}

              {!loading && loadError && (
                <div className="dashboard-error">
                  <p>{loadError}</p>

                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={fetchDashboardProjects}
                  >
                    Try Again
                  </button>
                </div>
              )}

              {!loading &&
                !loadError &&
                recentProjects.length === 0 && (
                  <div className="empty-projects">
                    <FolderKanban size={30} />

                    <p>No projects yet.</p>

                    <span>
                      Create your first project to get started.
                    </span>
                  </div>
                )}

              {!loading &&
                !loadError &&
                recentProjects.length > 0 && (
                  <div className="recent-projects-grid">
                    {recentProjects.map((project) => (
                      /*
                       * IMPORTANT:
                       * This is now a DIV, not a BUTTON.
                       * The project card is display-only and
                       * cannot be clicked.
                       */
                      <div
                        key={project.id}
                        className="recent-project-card"
                      >
                        <div className="project-card-top">
                          <div className="project-icon">
                            <FolderKanban size={18} />
                          </div>

                          <span className="project-menu">
                            ⋮
                          </span>
                        </div>

                        <div className="project-card-body">
                          <h3>
                            {project.name}
                          </h3>

                          {project.description && (
                            <p className="project-description">
                              {project.description}
                            </p>
                          )}

                          <div className="project-status-row">
                            <StatusBadge
                              status={project.status}
                            />
                          </div>
                        </div>

                        <div className="project-date">
                          <CalendarDays size={15} />

                          <span>
                            Dated ·{" "}
                            {formatDate(project.created_at)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
            </section>

            {/* RECENT ACTIVITY */}
            <section className="dashboard-section activity-section">
              <div className="section-heading">
                <h2>Recent Activity</h2>

                <p>
                  Recent workspace activity.
                </p>
              </div>

              {recentProjects.length > 0 ? (
                <div className="activity-list">

                  {recentProjects.map((project) => (
                    <div
                      className="activity-card"
                      key={`activity-${project.id}`}
                    >
                      <div className="activity-icon">
                        <FileText size={18} />
                      </div>

                      <div className="activity-content">
                        <strong>
                          {project.name} Project Created
                        </strong>

                        <span>
                          {formatDate(project.created_at)}
                        </span>
                      </div>
                    </div>
                  ))}

                </div>
              ) : (
                <div className="activity-card">
                  <div className="activity-icon">
                    <ClipboardList size={18} />
                  </div>

                  <div className="activity-content">
                    <strong>
                      No recent activity
                    </strong>

                    <span>
                      Activity will appear here when you create or update projects.
                    </span>
                  </div>
                </div>
              )}
            </section>

          </main>

          {/* RIGHT SIDE */}
          <aside className="dashboard-stats">

            <div className="stats-heading">
              <h2>
                WORKSPACE STATISTICS
              </h2>

              <p>
                Overview of your workspace.
              </p>
            </div>

            <div className="stats-grid">

              {/* PROJECTS */}
              <div className="stat-card">
                <div className="stat-icon">
                  <FolderKanban size={17} />
                </div>

                <p className="stat-label">
                  Projects
                </p>

                <strong className="stat-number">
                  {loading ? "—" : projects.length}
                </strong>

                <span className="stat-green">
                  {loading
                    ? ""
                    : `${activeProjectCount} Active`}
                </span>
              </div>

              {/* REQUIREMENTS */}
              <div className="stat-card stat-disabled">
                <div className="stat-icon">
                  <ClipboardList size={17} />
                </div>

                <p className="stat-label">
                  Requirements
                </p>

                <strong className="stat-number">
                  —
                </strong>

                <span>
                  Awaiting requirement data
                </span>
              </div>

              {/* PENDING REVIEWS */}
              <div className="stat-card stat-disabled">
                <div className="stat-icon">
                  <ClipboardList size={17} />
                </div>

                <p className="stat-label">
                  Pending Reviews
                </p>

                <strong className="stat-number">
                  —
                </strong>

                <span>
                  Awaiting review data
                </span>
              </div>

              {/* QUALITY */}
              <div className="stat-card stat-disabled">
                <div className="stat-icon">
                  <ClipboardList size={17} />
                </div>

                <p className="stat-label">
                  Overall Requirement Quality
                </p>

                <strong className="stat-number">
                  —
                </strong>

                <span>
                  Awaiting requirement analysis
                </span>
              </div>

            </div>

            {/* AI SUGGESTIONS */}
            <div className="ai-card">

              <div className="ai-card-header">

                <div className="ai-icon">
                  <Sparkles size={18} />
                </div>

                <div>
                  <h3>
                    AI Suggestions Generated
                  </h3>

                  <p>
                    Intelligent project insights
                  </p>
                </div>

                <Sparkles size={17} />

              </div>

              <div className="ai-card-bottom">

                <strong>
                  —
                </strong>

                <div className="ai-bars">
                  <span />
                  <span />
                  <span />
                  <span className="active-bar" />
                  <span />
                </div>

              </div>

              <p>
                AI insights will appear after requirement analysis.
              </p>

            </div>

          </aside>

        </div>
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