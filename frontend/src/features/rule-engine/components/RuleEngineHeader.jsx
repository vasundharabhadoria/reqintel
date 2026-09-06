import {
  LayoutDashboard,
  Folder,
  FileText,
  GitBranch,
  History,
} from "lucide-react";

import StatusBadge from "../../projects/components/StatusBadge";

function RuleEngineHeader({ project, projectLoading }) {
  const handleNoNavigation = (event) => {
    event.preventDefault();
  };

  return (
    <div className="rule-project-header">

      {/* PROJECT NAME + STATUS */}
      <div className="rule-project-title-row">
        {projectLoading ? (
          <h1>Loading project...</h1>
        ) : (
          <>
            <h1>{project?.name || "Project"}</h1>

            {project?.status && (
              <StatusBadge status={project.status} />
            )}
          </>
        )}
      </div>

      {/* PROJECT TABS */}
      <div className="rule-project-tabs">

        <button
          type="button"
          className="rule-project-tab"
          onClick={handleNoNavigation}
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
          className="rule-project-tab active"
          onClick={handleNoNavigation}
        >
          <FileText size={18} />
          <span>Requirements</span>
        </button>

        <button
          type="button"
          className="rule-project-tab"
          onClick={handleNoNavigation}
        >
          <GitBranch size={18} />
          <span>Traceability</span>
        </button>

        <button
          type="button"
          className="rule-project-tab"
          onClick={handleNoNavigation}
        >
          <History size={18} />
          <span>Versions</span>
        </button>

      </div>
    </div>
  );
}

export default RuleEngineHeader;