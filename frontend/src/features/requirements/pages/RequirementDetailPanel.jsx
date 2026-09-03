import { useCallback, useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";

import StatusPill from "../components/StatusPill";
import { createVersion, getRequirement, listVersions } from "../../../api/requirementsApi";
import { useToast } from "../../../hooks/useToast";
import "../styles/requirements.css";

function RequirementDetailPanel({ projectId, requirementId, onBack }) {
  const { showToast } = useToast();
  const [requirement, setRequirement] = useState(null);
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [newText, setNewText] = useState("");
  const [changeSummary, setChangeSummary] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [req, versionData] = await Promise.all([
        getRequirement(projectId, requirementId),
        listVersions(projectId, requirementId),
      ]);
      setRequirement(req);
      setVersions(versionData.items);
    } catch (err) {
      setLoadError(err.message || "Failed to load this requirement.");
    } finally {
      setLoading(false);
    }
  }, [projectId, requirementId]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  async function handleNewVersion(event) {
    event.preventDefault();
    if (!newText.trim()) return;

    setSubmitting(true);
    try {
      await createVersion(projectId, requirementId, {
        requirementText: newText.trim(),
        changeSummary: changeSummary.trim(),
      });
      showToast("New version created.", "success");
      setNewText("");
      setChangeSummary("");
      fetchAll();
    } catch (err) {
      showToast(err.message || "Failed to create the version.", "error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <button type="button" className="btn-link-back" onClick={onBack}>
        <ArrowLeft size={16} /> Back to Requirements
      </button>

      {loading && <p className="muted-text">Loading…</p>}

      {!loading && loadError && (
        <div className="table-state table-state-error">
          <p>{loadError}</p>
          <button type="button" className="btn btn-secondary" onClick={fetchAll}>
            Try Again
          </button>
        </div>
      )}

      {!loading && !loadError && requirement && (
        <>
          <div className="workspace-header">
            <div>
              <h2>{requirement.requirement_code}</h2>
              <p className="page-subtitle">{requirement.title || "Untitled"}</p>
            </div>
            <StatusPill status={requirement.status} />
          </div>

          <h3>Version History</h3>
          {[...versions].reverse().map((version) => (
            <div
              key={version.id}
              className={`req-version-item ${
                version.version_number === requirement.current_version_number ? "current" : ""
              }`}
            >
              <strong>v{version.version_number}</strong>
              {version.version_number === requirement.current_version_number && " (current)"}
              <p>{version.requirement_text}</p>
              {version.change_summary && (
                <p className="muted-text">{version.change_summary}</p>
              )}
              <p className="muted-text">{new Date(version.created_at).toLocaleString()}</p>
            </div>
          ))}

          <h3>Create New Version</h3>
          <form onSubmit={handleNewVersion}>
            <label className="form-field">
              <span>Requirement Text</span>
              <textarea
                rows={4}
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                disabled={submitting}
              />
            </label>
            <label className="form-field">
              <span>Change Summary (optional)</span>
              <input
                type="text"
                value={changeSummary}
                onChange={(e) => setChangeSummary(e.target.value)}
                maxLength={500}
                disabled={submitting}
              />
            </label>
            <button type="submit" className="btn btn-primary" disabled={submitting || !newText.trim()}>
              {submitting ? "Saving…" : "Save New Version"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}

export default RequirementDetailPanel;