import { useCallback, useEffect, useState } from "react";
import { Sparkles, X, CheckCircle2, Loader2 } from "lucide-react";

import StatusPill from "../components/StatusPill";
import {
  listRequirements,
  listSources,
  analyzeRequirements,
} from "../../../api/requirementsApi";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import "../styles/requirements.css";

const STATUS_OPTIONS = [
  "all",
  "pending",
  "approved",
  "rejected",
  "deprecated",
];

function RequirementsPanel({ projectId, onSelectRequirement }) {
  const [items, setItems] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchInput, setSearchInput] = useState("");
  const [showAnalyzeModal, setShowAnalyzeModal] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  const debouncedSearch = useDebouncedValue(searchInput, 300);

  const fetchRequirements = useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
      const [data, sourceData] = await Promise.all([
        listRequirements(projectId, {
          status: statusFilter,
          search: debouncedSearch,
        }),
        listSources(projectId),
      ]);

      setItems(data.items);
      setSources(sourceData.items || []);
    } catch (err) {
      setLoadError(err.message || "Failed to load requirements.");
    } finally {
      setLoading(false);
    }
  }, [projectId, statusFilter, debouncedSearch]);

  useEffect(() => {
    fetchRequirements();
  }, [fetchRequirements]);

  async function handleAnalyze() {
    setShowAnalyzeModal(true);
    setAnalyzing(true);
    setLoadError("");

    try {
      await analyzeRequirements(projectId);

      setAnalyzing(false);

      setTimeout(() => {
        window.location.href = `/projects/${projectId}/rule-engine`;
      }, 800);
    } catch (err) {
      setAnalyzing(false);
      setShowAnalyzeModal(false);
      setLoadError(err.message || "Failed to analyze requirements.");
    }
  }

  function handleCloseModal() {
    if (!analyzing) {
      setShowAnalyzeModal(false);
    }
  }

  return (
    <div className="requirements-panel">
      <div className="workspace-header">
        <div>
          <h2>Requirements</h2>
        </div>

        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            alignItems: "center",
          }}
        >
          <input
            type="search"
            placeholder="Search requirements…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt === "all" ? "All statuses" : opt}
              </option>
            ))}
          </select>

          <button
            type="button"
            className="btn btn-primary analyze-button"
            onClick={handleAnalyze}
            disabled={analyzing || items.length === 0}
          >
            <Sparkles size={17} />
            Analyze Requirements
          </button>
        </div>
      </div>

      {loading && (
        <p className="muted-text">
          Loading requirements…
        </p>
      )}

      {!loading && loadError && (
        <div className="table-state table-state-error">
          <p>{loadError}</p>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={fetchRequirements}
          >
            Try Again
          </button>
        </div>
      )}

      {!loading && !loadError && items.length === 0 && (
        <div className="table-state">
          <p>No requirements match your filters yet.</p>
        </div>
      )}

      {!loading && !loadError && items.length > 0 && (
  <div className="requirements-table-card">
    <div className="requirements-table-header">
      <div>Requirement ID</div>
      <div>Requirement</div>
      <div>Source Document</div>
      <div>Status</div>
    </div>

    <div className="requirements-table-body">
      {items.map((req) => {
        const source = sources.find(
          (item) => item.id === req.source_id
        );

        return (
          <button
            key={req.id}
            type="button"
            className="requirements-table-row"
            onClick={() => onSelectRequirement(req.id)}
          >
            <div className="requirement-id-cell">
              {req.requirement_code}
            </div>

            <div className="requirement-text-cell">
              <strong>{req.title || "Untitled"}</strong>

              <p>
                {req.current_requirement_text ||
                  "No requirement text available."}
              </p>
            </div>

            <div className="requirement-source-cell">
              <span>
                {source?.original_filename || "Unknown document"}
              </span>
            </div>

            <div className="requirement-status-cell">
              <StatusPill status={req.status} />
            </div>
          </button>
        );
      })}
    </div>
  </div>
)}

      {showAnalyzeModal && (
        <div className="analyze-modal-overlay">
          <div className="analyze-modal">
            <button
              type="button"
              className="analyze-modal-close"
              onClick={handleCloseModal}
              disabled={analyzing}
              aria-label="Close"
            >
              <X size={22} />
            </button>

            <div className="analyze-icon">
              {analyzing ? (
                <Sparkles size={28} />
              ) : (
                <CheckCircle2 size={28} />
              )}
            </div>

            <h2>
              {analyzing
                ? "Analyzing Requirements"
                : "Analysis Complete"}
            </h2>

            <p className="analyze-subtitle">
              {analyzing
                ? "Please wait while the Rule Engine analyzes your requirements."
                : "Your requirements have been analyzed successfully."}
            </p>

            <div className="analyze-progress">
              <div
                className={`analyze-progress-bar ${
                  analyzing ? "running" : "complete"
                }`}
              />
            </div>

            <div className="analyze-progress-text">
              {analyzing ? "Running Rule Engine..." : "100%"}
            </div>

            <div className="analyze-step active">
              <div className="step-icon">
                {analyzing ? (
                  <Loader2 size={20} className="spin" />
                ) : (
                  <CheckCircle2 size={20} />
                )}
              </div>

              <div className="step-content">
                <strong>Running Rule Engine</strong>

                <span>
                  {analyzing
                    ? "Validating requirements with business rules..."
                    : "Requirement validation completed."}
                </span>
              </div>

              <div className="step-status">
                {analyzing ? "In Progress" : "Completed"}
              </div>
            </div>

            {!analyzing && (
              <p className="redirect-message">
                Opening Rule Engine...
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default RequirementsPanel;