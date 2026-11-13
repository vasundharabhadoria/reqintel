import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Download,
  FileCode,
  FileSpreadsheet,
  FileText,
  Loader2,
  Trash2,
} from "lucide-react";

import AppShell from "../../../components/layout/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import { useToast } from "../../../hooks/useToast";
import { listProjects } from "../../../api/projectApi";
import {
  deleteReport,
  downloadReportFile,
  generateReport,
  listReports,
} from "../../../api/reportsApi";

import DeleteReportModal from "../components/DeleteReportModal";

import "../../projects/styles/projects.css";
import "../styles/reports.css";

const FORMATS = [
  { key: "pdf", label: "PDF", badge: "PDF", icon: FileText },
  { key: "xlsx", label: "Excel", badge: "XLSX", icon: FileSpreadsheet },
  { key: "html", label: "HTML", badge: "HTML", icon: FileCode },
];

const FORMAT_BY_KEY = Object.fromEntries(
  FORMATS.map((format) => [format.key, format])
);

function formatDateTime(isoString) {
  if (!isoString) return "—";

  return new Date(isoString).toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ReportsPage() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { showToast } = useToast();

  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");

  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [filterProject, setFilterProject] = useState("all");
  const [filterFormat, setFilterFormat] = useState("all");

  const [generating, setGenerating] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);

  const [deleteModal, setDeleteModal] = useState({
    open: false,
    report: null,
    submitting: false,
    error: "",
  });

  const handleSessionExpired = useCallback(async () => {
    showToast("Your session has expired. Please log in again.", "error");

    await logout();
    navigate("/login");
  }, [logout, navigate, showToast]);

  const fetchProjects = useCallback(async () => {
    setProjectsLoading(true);
    setProjectsError("");

    try {
      const response = await listProjects();

      setProjects(response.items);

      // With a single project there is nothing to choose.
      setSelectedProjectId((current) =>
        current || (response.items.length === 1 ? response.items[0].id : "")
      );
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }

      setProjectsError(err.message || "Failed to load projects.");
    } finally {
      setProjectsLoading(false);
    }
  }, [handleSessionExpired]);

  const fetchReports = useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
      const response = await listReports({
        projectId: filterProject,
        reportFormat: filterFormat,
      });

      setReports(response.items);
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }

      setLoadError(err.message || "Failed to load reports.");
    } finally {
      setLoading(false);
    }
  }, [filterProject, filterFormat, handleSessionExpired]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  async function handleGenerate(formatKey) {
    if (!selectedProjectId || generating) return;

    setGenerating(formatKey);

    try {
      const report = await generateReport({
        projectId: selectedProjectId,
        reportFormat: formatKey,
      });

      showToast(
        `${FORMAT_BY_KEY[formatKey].label} report generated for "${report.project_name}".`
      );

      await fetchReports();
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }

      showToast(
        err.message || "Unable to generate the report. Please try again.",
        "error"
      );
    } finally {
      setGenerating(null);
    }
  }

  async function handleDownload(report) {
    if (downloadingId) return;

    setDownloadingId(report.id);

    try {
      const blob = await downloadReportFile(report.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download = report.file_name;
      document.body.appendChild(link);
      link.click();
      link.remove();

      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }

      showToast(
        err.message || "Unable to download the report. Please try again.",
        "error"
      );

      // A 404 means the report or its file is gone: refresh the list.
      if (err.status === 404) {
        await fetchReports();
      }
    } finally {
      setDownloadingId(null);
    }
  }

  function openDeleteModal(report) {
    setDeleteModal({ open: true, report, submitting: false, error: "" });
  }

  function closeDeleteModal() {
    setDeleteModal({ open: false, report: null, submitting: false, error: "" });
  }

  async function handleDeleteConfirm() {
    const target = deleteModal.report;

    setDeleteModal((current) => ({ ...current, submitting: true, error: "" }));

    try {
      await deleteReport(target.id);

      showToast("Report deleted successfully.");

      closeDeleteModal();
      await fetchReports();
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }

      setDeleteModal((current) => ({
        ...current,
        submitting: false,
        error: err.message || "Unable to delete the report. Please try again.",
      }));
    }
  }

  const isFiltered = filterProject !== "all" || filterFormat !== "all";
  const canGenerate = Boolean(selectedProjectId) && !generating;

  return (
    <AppShell active="reports">
      <div className="page-header-row">
        <div>
          <h1>Reports</h1>
          <p className="page-subtitle">
            Generate and download requirement analysis reports for your projects
          </p>
        </div>
      </div>

      <section className="report-generate-card">
        <h2>Generate a report</h2>
        <p className="report-generate-hint">
          Choose a project, then pick a format. Reports are snapshots of the
          project&apos;s current requirements and available AI analysis.
        </p>

        {projectsLoading && <p className="muted-text">Loading projects...</p>}

        {!projectsLoading && projectsError && (
          <div className="table-state table-state-error">
            <p>{projectsError}</p>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={fetchProjects}
            >
              Try Again
            </button>
          </div>
        )}

        {!projectsLoading && !projectsError && projects.length === 0 && (
          <p className="report-empty-projects">
            You have no projects yet.{" "}
            <Link to="/projects">Create a project</Link> to generate reports.
          </p>
        )}

        {!projectsLoading && !projectsError && projects.length > 0 && (
          <div className="report-generate-row">
            <div className="report-field">
              <label htmlFor="report-project">Project</label>

              <select
                id="report-project"
                className="report-select"
                value={selectedProjectId}
                onChange={(event) => setSelectedProjectId(event.target.value)}
                disabled={Boolean(generating)}
              >
                <option value="">Select a project...</option>

                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                    {project.status !== "active" ? ` (${project.status})` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="report-format-buttons">
              {FORMATS.map((format) => {
                const Icon = format.icon;
                const isRunning = generating === format.key;

                return (
                  <button
                    key={format.key}
                    type="button"
                    className="btn btn-primary"
                    onClick={() => handleGenerate(format.key)}
                    disabled={!canGenerate}
                  >
                    {isRunning ? (
                      <Loader2 size={16} className="report-spinner" />
                    ) : (
                      <Icon size={16} />
                    )}
                    {isRunning ? "Generating..." : `Generate ${format.label}`}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </section>

      <div className="report-filters">
        <label className="status-filter">
          <span>Project:</span>

          <select
            value={filterProject}
            onChange={(event) => setFilterProject(event.target.value)}
          >
            <option value="all">All projects</option>

            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>

        <label className="status-filter">
          <span>Format:</span>

          <select
            value={filterFormat}
            onChange={(event) => setFilterFormat(event.target.value)}
          >
            <option value="all">All formats</option>

            {FORMATS.map((format) => (
              <option key={format.key} value={format.key}>
                {format.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="projects-table-card">
        {loading && (
          <div className="table-skeleton">
            {[0, 1, 2, 3].map((row) => (
              <div className="table-skeleton-row" key={row} />
            ))}
          </div>
        )}

        {!loading && loadError && (
          <div className="table-state table-state-error">
            <p>{loadError}</p>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={fetchReports}
            >
              Try Again
            </button>
          </div>
        )}

        {!loading && !loadError && reports.length === 0 && (
          <div className="table-state">
            <p>
              {isFiltered
                ? "No reports match your filters."
                : "No reports yet. Select a project above and generate your first report."}
            </p>
          </div>
        )}

        {!loading && !loadError && reports.length > 0 && (
          <>
            <table className="projects-table">
              <thead>
                <tr>
                  <th>Report</th>
                  <th>Project</th>
                  <th>Format</th>
                  <th>Generated</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {reports.map((report) => {
                  const format = FORMAT_BY_KEY[report.report_format];
                  const isDownloading = downloadingId === report.id;

                  return (
                    <tr key={report.id}>
                      <td>
                        <div className="report-file-cell">
                          {report.file_name}
                        </div>
                      </td>

                      <td>{report.project_name}</td>

                      <td>
                        <span
                          className={`report-format-badge report-format-badge-${report.report_format}`}
                        >
                          {format ? format.badge : report.report_format}
                        </span>
                      </td>

                      <td>{formatDateTime(report.generated_at)}</td>

                      <td>
                        <div className="report-actions">
                          <button
                            type="button"
                            className="btn btn-secondary btn-small"
                            onClick={() => handleDownload(report)}
                            disabled={Boolean(downloadingId)}
                          >
                            {isDownloading ? (
                              <Loader2 size={14} className="report-spinner" />
                            ) : (
                              <Download size={14} />
                            )}
                            {isDownloading ? "Downloading..." : "Download"}
                          </button>

                          <button
                            type="button"
                            className="btn btn-secondary btn-small"
                            onClick={() => openDeleteModal(report)}
                            aria-label={`Delete ${report.file_name}`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <div className="table-footer-row">
              Showing {reports.length} report{reports.length === 1 ? "" : "s"}
            </div>
          </>
        )}
      </div>

      <DeleteReportModal
        open={deleteModal.open}
        report={deleteModal.report}
        submitting={deleteModal.submitting}
        error={deleteModal.error}
        onClose={closeDeleteModal}
        onConfirm={handleDeleteConfirm}
      />
    </AppShell>
  );
}

export default ReportsPage;