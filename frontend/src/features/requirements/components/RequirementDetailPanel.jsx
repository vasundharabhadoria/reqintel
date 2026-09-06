import { useCallback, useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";

import StatusPill from "../components/StatusPill";
import { getRequirement, listSources } from "../../../api/requirementsApi";
import "../styles/requirements.css";

function RequirementDetailPanel({ projectId, requirementId, onBack }) {
  const [requirement, setRequirement] = useState(null);
  const [sourceDocument, setSourceDocument] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const fetchRequirementDetails = useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
      const [req, sourceData] = await Promise.all([
        getRequirement(projectId, requirementId),
        listSources(projectId),
      ]);

      setRequirement(req);

      const matchingSource = sourceData.items?.find(
        (source) => source.id === req.source_id
      );

      setSourceDocument(matchingSource || null);
    } catch (err) {
      setLoadError(err.message || "Failed to load this requirement.");
    } finally {
      setLoading(false);
    }
  }, [projectId, requirementId]);

  useEffect(() => {
    fetchRequirementDetails();
  }, [fetchRequirementDetails]);

  return (
    <div className="requirement-detail-page">
      <button type="button" className="btn-link-back" onClick={onBack}>
        <ArrowLeft size={16} /> Back to Requirements
      </button>

      {loading && <p className="muted-text">Loading...</p>}

      {!loading && loadError && (
        <div className="table-state table-state-error">
          <p>{loadError}</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={fetchRequirementDetails}
          >
            Try Again
          </button>
        </div>
      )}

      {!loading && !loadError && requirement && (
        <>
          <div className="requirement-detail-header">
            <div>
              <p className="requirement-detail-label">REQUIREMENT ID</p>
              <h2>{requirement.requirement_code}</h2>
              {requirement.title && (
                <p className="page-subtitle">{requirement.title}</p>
              )}
            </div>

            <StatusPill status={requirement.status} />
          </div>

          <div className="requirement-detail-card">
            <div className="requirement-detail-section">
              <span className="requirement-detail-label">
                SOURCE DOCUMENT
              </span>

              <p className="requirement-detail-source">
                {sourceDocument?.original_filename || "Source document unavailable"}
              </p>
            </div>

            <div className="requirement-detail-section">
              <span className="requirement-detail-label">
                REQUIREMENT
              </span>

              <div className="requirement-detail-text">
                {requirement.current_requirement_text ||
                  "No requirement text available."}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default RequirementDetailPanel;