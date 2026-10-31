import { useCallback, useEffect, useRef, useState } from "react";
import {
  Calendar,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileCode,
  FileText,
  FileType,
  Info,
  Layers,
  Pencil,
  Minus,
  Plus,
  User,
  X,
} from "lucide-react";

import { getRepositoryVersion } from "../../../api/versionsApi";
import {
  formatDate,
  formatFileSize,
  formatTime,
  formatVersion,
} from "../utils";

const PREVIEW_COUNT = 3;

function DocumentIcon({ type }) {
  const kind = String(type || "").toLowerCase();

  if (kind === "pdf") {
    return (
      <span className="ver-doc-icon ver-doc-pdf">
        <FileText size={18} />
      </span>
    );
  }

  if (kind === "docx") {
    return (
      <span className="ver-doc-icon ver-doc-docx">
        <FileType size={18} />
      </span>
    );
  }

  return (
    <span className="ver-doc-icon ver-doc-txt">
      <FileCode size={18} />
    </span>
  );
}

function SummaryTile({ icon, tone, label, value }) {
  return (
    <div className="ver-tile">
      <span className={`ver-tile-icon ver-tone-${tone}`}>{icon}</span>
      <div>
        <span className="ver-tile-label">{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function ChangeList({ title, tone, items }) {
  const [expanded, setExpanded] = useState(false);

  const visible = expanded ? items : items.slice(0, PREVIEW_COUNT);
  const hidden = items.length - visible.length;

  return (
    <div className="ver-change-box">
      <h4 className={`ver-change-title ver-change-title-${tone}`}>
        {title} ({items.length})
      </h4>

      {items.length === 0 && (
        <p className="ver-change-none">No requirements.</p>
      )}

      <ul>
        {visible.map((item) => (
          <li key={item.requirement_id}>
            <span className={`ver-bullet ver-bullet-${tone}`} />
            <span className="ver-change-code">{item.requirement_code}</span>
            <span className="ver-change-name" title={item.title || ""}>
              {item.title || "Untitled requirement"}
            </span>
          </li>
        ))}
      </ul>

      {hidden > 0 && (
        <button
          type="button"
          className="ver-more"
          onClick={() => setExpanded(true)}
        >
          +{hidden} more…
        </button>
      )}

      {expanded && items.length > PREVIEW_COUNT && (
        <button
          type="button"
          className="ver-more"
          onClick={() => setExpanded(false)}
        >
          Show less
        </button>
      )}
    </div>
  );
}

function RequirementsIncluded({ items }) {
  const [expanded, setExpanded] = useState(false);

  const visible = expanded ? items : items.slice(0, PREVIEW_COUNT);
  const hidden = items.length - visible.length;

  return (
    <div className="ver-reqs">
      <div className="ver-reqs-head">
        <span>ID</span>
        <span>Requirement Title</span>
      </div>

      <div className={expanded ? "ver-reqs-scroll" : undefined}>
        {visible.map((item) => (
          <div className="ver-reqs-row" key={item.requirement_id || item.requirement_code}>
            <span>{item.requirement_code}</span>
            <span title={item.title || ""}>
              {item.title || "Untitled requirement"}
            </span>
          </div>
        ))}
      </div>

      {items.length === 0 && (
        <p className="ver-change-none" style={{ padding: 16 }}>
          No requirements.
        </p>
      )}

      {hidden > 0 && (
        <button
          type="button"
          className="ver-reqs-more"
          onClick={() => setExpanded(true)}
        >
          <Plus size={14} /> {hidden} more requirement
          {hidden === 1 ? "" : "s"} <ChevronRight size={14} />
        </button>
      )}

      {expanded && items.length > PREVIEW_COUNT && (
        <button
          type="button"
          className="ver-reqs-more"
          onClick={() => setExpanded(false)}
        >
          Show less
        </button>
      )}
    </div>
  );
}

function VersionDetailsDrawer({ projectId, versionId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const open = Boolean(versionId);

  // Ignore a response that arrives after another version was opened.
  const latestRequest = useRef(0);

  const loadDetail = useCallback(async () => {
    if (!versionId) return;

    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;

    setLoading(true);
    setError("");

    try {
      const response = await getRepositoryVersion(projectId, versionId);
      if (requestId !== latestRequest.current) return;
      setDetail(response);
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      setError(err.message || "Failed to load version details.");
    } finally {
      if (requestId === latestRequest.current) {
        setLoading(false);
      }
    }
  }, [projectId, versionId]);

  useEffect(() => {
    // Never show the previous version's data while a new one loads.
    setDetail(null);
    loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    if (!open) return undefined;

    function handleKeyDown(event) {
      if (event.key === "Escape") onClose();
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ver-overlay" onMouseDown={onClose}>
      <aside
        className="ver-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Version details"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="ver-drawer-header">
          <h3>Version Details</h3>
          <button
            type="button"
            className="ver-drawer-close"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </header>

        <div className="ver-drawer-body">
          {loading && !detail && (
            <p className="ver-drawer-state">Loading version details...</p>
          )}

          {error && (
            <div className="ver-drawer-state">
              <p>{error}</p>
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={loadDetail}
              >
                Try Again
              </button>
            </div>
          )}

          {detail && !error && (
            <>
              <div className="ver-drawer-title">
                <span className="ver-drawer-badge">
                  <Layers size={26} />
                </span>
                <h2>{formatVersion(detail.version_number)}</h2>
                <span className="ver-badge">
                  {detail.is_current
                    ? "Latest Repository"
                    : "Previous Repository"}
                </span>
              </div>

              <div className="ver-meta">
                <div className="ver-meta-item">
                  <Calendar size={20} />
                  <div>
                    <span>Created On</span>
                    <strong>{formatDate(detail.created_at)}</strong>
                    <em>{formatTime(detail.created_at)}</em>
                  </div>
                </div>

                <div className="ver-meta-item">
                  <div>
                    <span>Status</span>
                    <strong
                      className={detail.is_current ? "ver-status-current" : ""}
                    >
                      <span
                        className={`ver-pill-dot ${
                          detail.is_current ? "" : "is-previous"
                        }`}
                      />
                      {detail.is_current ? "Current" : "Previous"}
                    </strong>
                  </div>
                </div>

                <div className="ver-meta-item">
                  <User size={20} />
                  <div>
                    <span>Approved By</span>
                    <strong>{detail.created_by_name || "—"}</strong>
                    {detail.created_by_role && (
                      <em>
                        {detail.created_by_role
                          .replace(/_/g, " ")
                          .replace(/\b\w/g, (c) => c.toUpperCase())}
                      </em>
                    )}
                  </div>
                </div>
              </div>

              <section>
                <h4 className="ver-section-title">Repository Summary</h4>

                <div className="ver-tiles">
                  <SummaryTile
                    tone="blue"
                    icon={<FileText size={20} />}
                    label="Total Requirements"
                    value={detail.total_requirements}
                  />
                  <SummaryTile
                    tone="green"
                    icon={<CheckCircle2 size={20} />}
                    label="Approved"
                    value={detail.approved_requirements}
                  />
                  <SummaryTile
                    tone="orange"
                    icon={<Clock size={20} />}
                    label="Pending Review"
                    value={detail.pending_requirements}
                  />
                </div>

                {!detail.is_baseline && (
                  <div className="ver-tiles">
                    <SummaryTile
                      tone="green"
                      icon={<Plus size={20} />}
                      label="New Requirements"
                      value={detail.new_count}
                    />
                    <SummaryTile
                      tone="purple"
                      icon={<Pencil size={20} />}
                      label="Modified Requirements"
                      value={detail.modified_count}
                    />
                    <SummaryTile
                      tone="red"
                      icon={<Minus size={20} />}
                      label="Deleted Requirements"
                      value={detail.deleted_count}
                    />
                  </div>
                )}

                {detail.is_baseline && (
                  <div className="ver-banner">
                    <Info size={18} />
                    <p>
                      This is the initial (baseline) repository version.
                      <br />
                      There is no previous version available for comparison.
                    </p>
                  </div>
                )}
              </section>

              {detail.is_baseline ? (
                <section>
                  <h4 className="ver-section-title">
                    Requirements Included ({detail.requirements.length})
                  </h4>
                  <RequirementsIncluded items={detail.requirements} />
                </section>
              ) : (
                <section>
                  <h4 className="ver-section-title">
                    Version Changes <Info size={15} />
                  </h4>

                  <div className="ver-changes-grid">
                    <ChangeList
                      title="New Requirements"
                      tone="green"
                      items={detail.changes.new}
                    />
                    <ChangeList
                      title="Modified Requirements"
                      tone="purple"
                      items={detail.changes.modified}
                    />
                    <ChangeList
                      title="Deleted Requirements"
                      tone="red"
                      items={detail.changes.deleted}
                    />
                  </div>
                </section>
              )}

              <section>
                <h4 className="ver-section-title">
                  Documents Included ({detail.documents.length})
                </h4>

                <div className="ver-docs">
                  {detail.documents.length === 0 && (
                    <p className="ver-change-none">No documents.</p>
                  )}

                  {detail.documents.map((doc) => (
                    <div className="ver-doc-row" key={doc.id}>
                      <DocumentIcon type={doc.source_type} />
                      <span className="ver-doc-name" title={doc.filename}>
                        {doc.filename}
                      </span>
                      <span className="ver-doc-meta">
                        {String(doc.source_type || "").toUpperCase()}
                        {doc.size_bytes !== null &&
                          doc.size_bytes !== undefined &&
                          ` · ${formatFileSize(doc.size_bytes)}`}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>

        <footer className="ver-drawer-footer">
          <button
            type="button"
            className="btn btn-primary"
            disabled
            title="Repository reports are coming soon"
          >
            <FileText size={18} />
            Generate Repository Report
          </button>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
          >
            Close
          </button>
        </footer>
      </aside>
    </div>
  );
}

export default VersionDetailsDrawer;
