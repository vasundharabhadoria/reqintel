import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Layers,
  Pencil,
  Search,
} from "lucide-react";

import { listRepositoryVersions } from "../../../api/versionsApi";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import VersionDetailsDrawer from "../components/VersionDetailsDrawer";
import { formatDate, formatTime, formatVersion } from "../utils";
import "../styles/versions.css";

const PAGE_SIZES = [10, 20, 50];

function SummaryCard({ icon, tone, value, label }) {
  return (
    <div className="ver-card">
      <span className={`ver-card-icon ver-tone-${tone}`}>{icon}</span>
      <div className="ver-card-text">
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

function ChangesSummary({ version }) {
  // The first version has nothing to compare against.
  if (version.version_number === 1) {
    return <span className="ver-initial">Initial Repository</span>;
  }

  const hasCounts =
    version.new_count > 0 ||
    version.modified_count > 0 ||
    version.deleted_count > 0;

  if (!hasCounts) {
    return (
      <span className="ver-changes-text">
        {version.change_summary || "No changes"}
      </span>
    );
  }

  return (
    <ul className="ver-changes">
      <li className="ver-change-new">
        <span className="ver-mark">+</span>
        {version.new_count} New
      </li>
      <li className="ver-change-modified">
        <span className="ver-mark">●</span>
        {version.modified_count} Modified
      </li>
      <li className="ver-change-deleted">
        <span className="ver-mark">−</span>
        {version.deleted_count} Deleted
      </li>
    </ul>
  );
}

function pageWindow(current, last) {
  const start = Math.max(1, Math.min(current - 2, last - 4));
  const end = Math.min(last, start + 4);
  const pages = [];

  for (let page = start; page <= end; page += 1) {
    pages.push(page);
  }

  return pages;
}

function VersionsPanel({ projectId }) {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 400);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState(null);

  // Ignore responses that arrive after a newer request was started.
  const latestRequest = useRef(0);

  const loadVersions = useCallback(async () => {
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;

    setLoading(true);
    setError("");

    try {
      const response = await listRepositoryVersions(projectId, {
        search: debouncedSearch,
        page,
        pageSize,
      });

      if (requestId !== latestRequest.current) return;
      setData(response);
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      setError(err.message || "Failed to load repository versions.");
    } finally {
      if (requestId === latestRequest.current) {
        setLoading(false);
      }
    }
  }, [projectId, debouncedSearch, page, pageSize]);

  useEffect(() => {
    loadVersions();
  }, [loadVersions]);

  const summary = data?.summary;
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  const firstShown = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastShown = Math.min(page * pageSize, total);
  const hasNoVersionsAtAll =
    !loading && !error && summary?.total_versions === 0;

  return (
    <div className="ver-panel">
      <div className="ver-header">
        <h2>Version Management</h2>
        <p>
          View and manage repository versions created after requirement
          review and approval.
        </p>
      </div>

      <div className="ver-cards">
        <SummaryCard
          tone="purple"
          icon={<Layers size={24} />}
          value={summary?.total_versions ?? "—"}
          label="Total Versions"
        />
        <SummaryCard
          tone="green"
          icon={<CheckCircle2 size={24} />}
          value={formatVersion(summary?.current_version)}
          label="Latest Version"
        />
        <SummaryCard
          tone="orange"
          icon={<Clock size={24} />}
          value={formatVersion(summary?.previous_version)}
          label="Previous Version"
        />
        <SummaryCard
          tone="green"
          icon={<CheckCircle2 size={24} />}
          value={summary?.approved_requirements ?? "—"}
          label="Approved Requirements"
        />
        <SummaryCard
          tone="blue"
          icon={<Pencil size={22} />}
          value={summary?.modified_requirements ?? "—"}
          label="Modified Requirements"
        />
        <SummaryCard
          tone="orange"
          icon={<Clock size={22} />}
          value={summary?.pending_requirements ?? "—"}
          label="Pending Review"
        />
      </div>

      <div className="ver-search">
        <Search size={18} />
        <input
          type="text"
          value={search}
          placeholder="Search by version number, repository version or date..."
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />
      </div>

      {error && (
        <div className="table-state table-state-error">
          <p>{error}</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={loadVersions}
          >
            Try Again
          </button>
        </div>
      )}

      {!error && (
        <div className={`ver-table-wrap ${loading && data ? "is-loading" : ""}`}>
          <table className="ver-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Version</th>
                <th>Repository Status</th>
                <th>Created On</th>
                <th>Requirements</th>
                <th>Changes Summary</th>
                <th>Action</th>
              </tr>
            </thead>

            <tbody>
              {loading && !data && (
                <tr>
                  <td colSpan={7} className="ver-empty">
                    Loading versions...
                  </td>
                </tr>
              )}

              {hasNoVersionsAtAll && (
                <tr>
                  <td colSpan={7} className="ver-empty">
                    No repository versions yet. A version is created
                    automatically after you run <strong>Analyze</strong> on
                    the Requirements tab.
                  </td>
                </tr>
              )}

              {!loading && !hasNoVersionsAtAll && items.length === 0 && (
                <tr>
                  <td colSpan={7} className="ver-empty">
                    No versions match your search.
                  </td>
                </tr>
              )}

              {items.map((version, index) => (
                <tr key={version.id}>
                  <td>{(page - 1) * pageSize + index + 1}</td>
                  <td className="ver-version-cell">
                    {formatVersion(version.version_number)}
                  </td>
                  <td>
                    <span
                      className={`ver-pill ${
                        version.is_current ? "is-current" : "is-previous"
                      }`}
                    >
                      <span className="ver-pill-dot" />
                      {version.is_current ? "Current" : "Previous"}
                    </span>
                  </td>
                  <td>
                    <div className="ver-date">
                      <span>{formatDate(version.created_at)}</span>
                      <em>{formatTime(version.created_at)}</em>
                    </div>
                  </td>
                  <td className="ver-count-cell">{version.total_requirements}</td>
                  <td>
                    <ChangesSummary version={version} />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="ver-view-btn"
                      onClick={() => setSelectedVersionId(version.id)}
                    >
                      View Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!error && total > 0 && (
        <div className="ver-footer">
          <span className="ver-showing">
            Showing {firstShown} to {lastShown} of {total} version
            {total === 1 ? "" : "s"}
          </span>

          <div className="ver-pager">
            <button
              type="button"
              className="ver-pager-btn"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft size={16} />
            </button>

            {pageWindow(page, lastPage).map((number) => (
              <button
                key={number}
                type="button"
                className={`ver-pager-btn ${
                  number === page ? "is-active" : ""
                }`}
                onClick={() => setPage(number)}
              >
                {number}
              </button>
            ))}

            <button
              type="button"
              className="ver-pager-btn"
              disabled={page >= lastPage}
              onClick={() => setPage(page + 1)}
              aria-label="Next page"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          <label className="ver-page-size">
            <select
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(1);
              }}
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size} / page
                </option>
              ))}
            </select>
            <ChevronDown size={16} />
          </label>
        </div>
      )}

      <VersionDetailsDrawer
        projectId={projectId}
        versionId={selectedVersionId}
        onClose={() => setSelectedVersionId(null)}
      />
    </div>
  );
}

export default VersionsPanel;
