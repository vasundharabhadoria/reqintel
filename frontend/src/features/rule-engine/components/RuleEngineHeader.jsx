import {
  LayoutDashboard,
  Folder,
  FileText,
  GitBranch,
  History,
} from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import StatusBadge from "../../projects/components/StatusBadge";

function RuleEngineHeader({
  project,
  projectLoading,
  repositoryVersion,
  activeTab = "requirements",
}) {
  const navigate = useNavigate();
  const { projectId } = useParams();

  const handleNoNavigation = (event) => {
    event.preventDefault();
  };

  return (
    <div className="rule-project-header">
      <div className="rule-project-title-row">
        {projectLoading ? (
          <h1>Loading project...</h1>
        ) : (
          <>
            <h1>{project?.name || "Project"}</h1>

            {project?.status && (
              <StatusBadge status={project.status} />
            )}

            {repositoryVersion && (
              <span className="rule-repository-version">
                Active · Repository Version {repositoryVersion}
              </span>
            )}
          </>
        )}
      </div>

      <div className="rule-project-tabs">
        <button
          type="button"
          className={`rule-project-tab ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => navigate(`/projects/${projectId}`)}
        >
          <LayoutDashboard size={18} />
          <span>Overview</span>
        </button>

        <button
          type="button"
          className="rule-project-tab"
          onClick={handleNoNavigation}
        >
          <Folder size={18} />
          <span>Documents</span>
        </button>

        <button
          type="button"
          className={`rule-project-tab ${activeTab === "requirements" ? "active" : ""}`}
          onClick={() => navigate(`/projects/${projectId}/rule-engine`)}
        >
          <FileText size={18} />
          <span>Requirements</span>
        </button>

        <button
          type="button"
          className={`rule-project-tab ${activeTab === "traceability" ? "active" : ""}`}
          onClick={() => navigate(`/projects/${projectId}/traceability`)}
        >
          <GitBranch size={18} />
          <span>Traceability</span>
        </button>

        <button
          type="button"
          className="rule-project-tab"
          onClick={() => navigate(`/projects/${projectId}?tab=versions`)}
        >
          <History size={18} />
          <span>Versions</span>
        </button>
      </div>
    </div>
  );
}

export default RuleEngineHeader;