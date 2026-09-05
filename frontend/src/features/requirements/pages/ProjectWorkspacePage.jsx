import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import AppShell from "../../../components/layout/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import { useToast } from "../../../hooks/useToast";
import { getProject } from "../../../api/projectApi";
import StatusBadge from "../../projects/components/StatusBadge";
import SourcesPanel from "../../requirements/pages/SourcesPanel";
import RequirementsPanel from "../../requirements/pages/RequirementsPanel";
import RequirementDetailPanel from "../../requirements/pages/RequirementDetailPanel";
import "../../projects/styles/projects.css";

function formatDate(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}

function ProjectWorkspacePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { showToast } = useToast();

  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [activeTab, setActiveTab] = useState("sources");
  const [selectedRequirementId, setSelectedRequirementId] = useState(null);

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

  return (
    <AppShell 
      active={activeTab === "requirements" ? "requirements" : "projects"}
    >
      <button type="button" className="btn-link-back" onClick={() => navigate("/projects")}>
        <ArrowLeft size={16} /> Back to Projects
      </button>

      {loading && <p className="muted-text">Loading project...</p>}

      {!loading && loadError && (
        <div className="table-state table-state-error">
          <p>{loadError}</p>
          <button type="button" className="btn btn-secondary" onClick={fetchProject}>
            Try Again
          </button>
        </div>
      )}

      {!loading && !loadError && project && (
        <div className="workspace-card">
          <div className="workspace-header">
            <div>
              <h1>{project.name}</h1>
              <p className="page-subtitle">{project.client_name || "No client name set"}</p>
            </div>
            <StatusBadge status={project.status} />
          </div>

          <dl className="workspace-meta">
            <div>
              <dt>Project Type</dt>
              <dd>{project.project_type || "—"}</dd>
            </div>
            <div>
              <dt>Created On</dt>
              <dd>{formatDate(project.created_at)}</dd>
            </div>
            <div>
              <dt>Last Updated</dt>
              <dd>{formatDate(project.updated_at)}</dd>
            </div>
          </dl>

          <div className="workspace-description">
            <h2>Description</h2>
            <p>{project.description || "No description provided."}</p>
          </div>

          <div className="req-tabs">
            <button
              type="button"
              className={`req-tab ${activeTab === "sources" ? "active" : ""}`}
              onClick={() => setActiveTab("sources")}
            >
              Documents &amp; Sources
            </button>
            <button
              type="button"
              className={`req-tab ${activeTab === "requirements" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("requirements");
                setSelectedRequirementId(null);
              }}
            >
              Requirements
            </button>
          </div>

          {activeTab === "sources" && <SourcesPanel projectId={projectId} />}

          {activeTab === "requirements" && !selectedRequirementId && (
            <RequirementsPanel
              projectId={projectId}
              onSelectRequirement={setSelectedRequirementId}
            />
          )}

          {activeTab === "requirements" && selectedRequirementId && (
            <RequirementDetailPanel
              projectId={projectId}
              requirementId={selectedRequirementId}
              onBack={() => setSelectedRequirementId(null)}
            />
          )}
        </div>
      )}
    </AppShell>
  );
}

export default ProjectWorkspacePage;