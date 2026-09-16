import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import AppShell from "../../../components/layout/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import { useToast } from "../../../hooks/useToast";
import { getProject } from "../../../api/projectApi";
import StatusBadge from "../components/StatusBadge";
import "../styles/projects.css";

function ProjectWorkspacePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { showToast } = useToast();

  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const fetchProject = useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
      const data = await getProject(projectId);
      setProject(data);
    } catch (err) {
      if (err.status === 401) {
        showToast("Your session has expired. Please log in again.", "error");
        await logout();
        navigate("/login");
        return;
      }

      if (err.status === 404) {
        setLoadError("This project doesn't exist or you don't have access to it.");
      } else {
        setLoadError(err.message || "Failed to load this project.");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, logout, navigate, showToast]);

  useEffect(() => {
    fetchProject();
  }, [fetchProject]);

  const goToTab = (tab) => {
    if (tab === "Overview") {
      navigate(`/projects/${projectId}`);
    } else if (tab === "Documents") {
      navigate(`/projects/${projectId}/documents`);
    } else if (tab === "Requirements") {
      navigate(`/projects/${projectId}/requirements`);
    } else if (tab === "Traceability") {
      navigate(`/projects/${projectId}/traceability`);
    } else if (tab === "Versions") {
      navigate(`/projects/${projectId}/versions`);
    }
  };

  return (
    <AppShell active="projects">
      <button
        type="button"
        className="btn-link-back"
        onClick={() => navigate("/projects")}
      >
        <ArrowLeft size={16} /> Back to Projects
      </button>

      {loading && <p className="muted-text">Loading project...</p>}

      {!loading && loadError && (
        <div className="table-state table-state-error">
          <p>{loadError}</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={fetchProject}
          >
            Try Again
          </button>
        </div>
      )}

      {!loading && !loadError && project && (
        <div className="workspace-card">
          <div className="workspace-header">
            <div>
              <h1>{project.name}</h1>
              <p className="page-subtitle">
                {project.client_name || "No client name set"}
              </p>
            </div>

            <StatusBadge status={project.status} />
          </div>

          <nav className="workspace-tabs">
            <button
              type="button"
              className="workspace-tab active"
              onClick={() => goToTab("Overview")}
            >
              Overview
            </button>

            <button
              type="button"
              className="workspace-tab"
              onClick={() => goToTab("Documents")}
            >
              Documents
            </button>

            <button
              type="button"
              className="workspace-tab"
              onClick={() => goToTab("Requirements")}
            >
              Requirements
            </button>

            <button
              type="button"
              className="workspace-tab"
              onClick={() => goToTab("Traceability")}
            >
              Traceability
            </button>

            <button
              type="button"
              className="workspace-tab"
              onClick={() => goToTab("Versions")}
            >
              Versions
            </button>
          </nav>

          <div className="workspace-overview">
            <h2>Overview</h2>
            <p>
              {project.description || "No description provided."}
            </p>
          </div>
        </div>
      )}
    </AppShell>
  );
}

export default ProjectWorkspacePage;