import { useCallback, useEffect, useState } from "react";

import StatusPill from "../components/StatusPill";
import { listRequirements } from "../../../api/requirementsApi";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import "../styles/requirements.css";

const STATUS_OPTIONS = ["all", "pending", "approved", "rejected", "deprecated"];

function RequirementsPanel({ projectId, onSelectRequirement }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  const fetchRequirements = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const data = await listRequirements(projectId, {
        status: statusFilter,
        search: debouncedSearch,
      });
      setItems(data.items);
    } catch (err) {
      setLoadError(err.message || "Failed to load requirements.");
    } finally {
      setLoading(false);
    }
  }, [projectId, statusFilter, debouncedSearch]);

  useEffect(() => {
    fetchRequirements();
  }, [fetchRequirements]);

  return (
    <div>
      <div className="workspace-header">
        <h2>Requirements</h2>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="search"
            placeholder="Search requirements…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt === "all" ? "All statuses" : opt}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <p className="muted-text">Loading requirements…</p>}

      {!loading && loadError && (
        <div className="table-state table-state-error">
          <p>{loadError}</p>
          <button type="button" className="btn btn-secondary" onClick={fetchRequirements}>
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
        <div className="req-list">
          {items.map((req) => (
            <button
              key={req.id}
              type="button"
              className="req-list-row"
              onClick={() => onSelectRequirement(req.id)}
            >
              <div>
                <strong>{req.requirement_code}</strong> — {req.title || "Untitled"}
                <div className="muted-text">
                  {req.current_requirement_text
                    ? req.current_requirement_text.slice(0, 120)
                    : "No version text yet."}
                </div>
              </div>
              <StatusPill status={req.status} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default RequirementsPanel;