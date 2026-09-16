import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  Sparkles,
  X,
  CheckCircle2,
  Loader2,
  FileText,
  FileType,
  FileCode,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

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

function RequirementsPanel({
  projectId,
  onSelectRequirement,
}) {
  const navigate = useNavigate();

  const [items, setItems] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [statusFilter, setStatusFilter] =
    useState("all");
  const [searchInput, setSearchInput] = useState("");
  const [showAnalyzeModal, setShowAnalyzeModal] =
    useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  const debouncedSearch = useDebouncedValue(
    searchInput,
    300
  );

  const fetchRequirements = useCallback(async () => {
    if (!projectId) {
      return;
    }

    setLoading(true);
    setLoadError("");

    try {
      const [
        requirementsData,
        sourcesData,
      ] = await Promise.all([
        listRequirements(projectId, {
          status: statusFilter,
          search: debouncedSearch,
        }),
        listSources(projectId),
      ]);

      setItems(
        requirementsData.items || []
      );

      setSources(
        sourcesData.items || []
      );
    } catch (err) {
      setLoadError(
        err.message ||
          "Failed to load requirements."
      );
    } finally {
      setLoading(false);
    }
  }, [
    projectId,
    statusFilter,
    debouncedSearch,
  ]);

  useEffect(() => {
    fetchRequirements();
  }, [fetchRequirements]);

  /*
   * Create a source lookup once instead of calling
   * sources.find() for every requirement row.
   */
  const sourcesById = useMemo(() => {
    const map = new Map();

    for (const source of sources) {
      map.set(source.id, source);
    }

    return map;
  }, [sources]);

  const handleAnalyze = useCallback(async () => {
    if (
      analyzing ||
      loading ||
      items.length === 0
    ) {
      return;
    }

    /*
     * Show the modal immediately.
     * The actual Rule Engine request happens after
     * the state update, so the user gets immediate
     * visual feedback.
     */
    setShowAnalyzeModal(true);
    setAnalyzing(true);
    setLoadError("");

    try {
      const analysisData =
        await analyzeRequirements(projectId);

      /*
       * Store the already-computed result so the
       * RuleEngine page does not execute the analysis
       * again.
       */
      sessionStorage.setItem(
        `rule-engine-analysis-${projectId}`,
        JSON.stringify(analysisData)
      );

      /*
       * Use React Router instead of window.location.href.
       * This avoids a complete browser reload.
       */
      navigate(
        `/projects/${projectId}/rule-engine`,
        {
          replace: true,
        }
      );
    } catch (err) {
      console.error(
        "Failed to analyze requirements:",
        err
      );

      setAnalyzing(false);
      setShowAnalyzeModal(false);

      setLoadError(
        err.message ||
          "Failed to analyze requirements."
      );
    }
  }, [
    analyzing,
    loading,
    items.length,
    projectId,
    navigate,
  ]);

  const handleCloseModal = useCallback(() => {
    if (!analyzing) {
      setShowAnalyzeModal(false);
    }
  }, [analyzing]);

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
            onChange={(e) =>
              setSearchInput(e.target.value)
            }
          />

          <select
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value)
            }
          >
            {STATUS_OPTIONS.map((opt) => (
              <option
                key={opt}
                value={opt}
              >
                {opt === "all"
                  ? "All statuses"
                  : opt}
              </option>
            ))}
          </select>

          <button
            type="button"
            className="btn btn-primary analyze-button"
            onClick={handleAnalyze}
            disabled={
              analyzing ||
              loading ||
              items.length === 0
            }
          >
            {analyzing ? (
              <Loader2
                size={17}
                className="spin"
              />
            ) : (
              <Sparkles size={17} />
            )}

            {analyzing
              ? "Analyzing..."
              : "Analyze Requirements"}
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

      {!loading &&
        !loadError &&
        items.length === 0 && (
          <div className="table-state">
            <p>
              No requirements match your filters yet.
            </p>
          </div>
        )}

      {!loading &&
        !loadError &&
        items.length > 0 && (
          <div className="requirements-table-card">
            <div className="requirements-table-header">
              <div>Requirement ID</div>
              <div>Requirement</div>
              <div>Source Document</div>
              <div>Status</div>
            </div>

            <div className="requirements-table-body">
              {items.map((req) => {
                const source =
                  sourcesById.get(
                    req.source_id
                  );

                return (
                  <button
                    key={req.id}
                    type="button"
                    className="requirements-table-row"
                    onClick={() =>
                      onSelectRequirement(
                        req.id
                      )
                    }
                  >
                    <div className="requirement-id-cell">
                      {req.requirement_code}
                    </div>

                    <div className="requirement-text-cell">
                      <strong>
                        {req.title ||
                          "Untitled"}
                      </strong>

                      <p>
                        {req.current_requirement_text ||
                          "No requirement text available."}
                      </p>
                    </div>

                    <div className="requirement-source-cell">
                        <span className="requirement-source-icon">
                          <FileText size={16} />
                        </span>
                        <span>{source?.original_filename || "Unknown document"}</span>
                      </div>

                    <div className="requirement-status-cell">
                       <span className={`requirement-status-badge status-${req.status}`}>
                          {req.status}
                        </span>
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
                  analyzing
                    ? "running"
                    : "complete"
                }`}
              />
            </div>

            <div className="analyze-progress-text">
              {analyzing
                ? "Running Rule Engine..."
                : "100%"}
            </div>

            <div className="analyze-step active">
              <div className="step-icon">
                {analyzing ? (
                  <Loader2
                    size={20}
                    className="spin"
                  />
                ) : (
                  <CheckCircle2 size={20} />
                )}
              </div>

              <div className="step-content">
                <strong>
                  Running Rule Engine
                </strong>

                <span>
                  {analyzing
                    ? "Validating requirements with business rules..."
                    : "Requirement validation completed."}
                </span>
              </div>

              <div className="step-status">
                {analyzing
                  ? "In Progress"
                  : "Completed"}
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