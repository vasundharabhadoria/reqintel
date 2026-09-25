import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, LayoutDashboard, Folder, FileText, GitBranch, History } from "lucide-react";

import AppShell from "../../../components/layout/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import { useToast } from "../../../hooks/useToast";
import { getProject } from "../../../api/projectApi";
import StatusBadge from "../../projects/components/StatusBadge";
import SourcesPanel from "../../requirements/pages/SourcesPanel";
import RequirementsPanel from "../../requirements/pages/RequirementsPanel";
import RequirementDetailPanel from "../../requirements/pages/RequirementDetailPanel";
import "../../projects/styles/projects.css";

function ProjectWorkspacePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { showToast } = useToast();

  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [activeTab, setActiveTab] = useState("documents");
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

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setSelectedRequirementId(null);

    if (tab === "overview") {
      navigate(`/projects/${projectId}`);
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

          <div className="workspace-tabs">
  <button
    type="button"
    className={`workspace-tab ${
      activeTab === "overview" ? "active" : ""
    }`}
    onClick={() => handleTabChange("overview")}
  >
    <LayoutDashboard size={20} />
    <span>Overview</span>
  </button>

  <button
    type="button"
    className={`workspace-tab ${
      activeTab === "documents" ? "active" : ""
    }`}
    onClick={() => handleTabChange("documents")}
  >
    <Folder size={20} />
    <span>Documents</span>
  </button>

  <button
    type="button"
    className={`workspace-tab ${
      activeTab === "requirements" ? "active" : ""
    }`}
    onClick={() => handleTabChange("requirements")}
  >
    <FileText size={20} />
    <span>Requirements</span>
  </button>

  <button
    type="button"
    className={`workspace-tab ${
      activeTab === "traceability" ? "active" : ""
    }`}
    onClick={() => handleTabChange("traceability")}
  >
    <GitBranch size={20} />
    <span>Traceability</span>
  </button>

  <button
    type="button"
    className={`workspace-tab ${
      activeTab === "versions" ? "active" : ""
    }`}
    onClick={() => handleTabChange("versions")}
  >
    <History size={20} />
    <span>Versions</span>
  </button>
</div>

          {activeTab === "overview" && (
            <div className="workspace-overview">
              <h2>Overview</h2>
              <p>
                {project.description || "No description provided."}
              </p>
            </div>
          )}

          {activeTab === "documents" && (
            <SourcesPanel projectId={projectId} />
          )}

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

          {activeTab === "traceability" && (
            <div className="workspace-placeholder">
              <h2>Traceability</h2>
              <p>Traceability workspace coming soon.</p>
            </div>
          )}

          {activeTab === "versions" && (
            <div className="workspace-placeholder">
              <h2>Versions</h2>
              <p>Versions workspace coming soon.</p>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}

export default ProjectWorkspacePage;