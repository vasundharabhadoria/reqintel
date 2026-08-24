import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search } from "lucide-react";

import AppShell from "../../../components/layout/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import { useToast } from "../../../hooks/useToast";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import { archiveProject, createProject, listProjects, updateProject } from "../../../api/projectApi";
import ProjectsTable from "../components/ProjectsTable";
import ProjectFormModal from "../components/ProjectFormModal";
import ArchiveConfirmModal from "../components/ArchiveConfirmModal";
import "../styles/projects.css";

function ProjectsPage() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { showToast } = useToast();

  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 400);
  const [statusFilter, setStatusFilter] = useState("all");

  const [formModal, setFormModal] = useState({ open: false, mode: "create", project: null });
  const [archiveModal, setArchiveModal] = useState({
    open: false,
    project: null,
    submitting: false,
    error: "",
  });

  const handleSessionExpired = useCallback(async () => {
    showToast("Your session has expired. Please log in again.", "error");
    await logout();
    navigate("/login");
  }, [logout, navigate, showToast]);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
      const response = await listProjects({
        status: statusFilter,
        search: debouncedSearch.trim() || undefined,
      });
      setProjects(response.items);
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }
      setLoadError(err.message || "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, debouncedSearch, handleSessionExpired]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  function openCreateModal() {
    setFormModal({ open: true, mode: "create", project: null });
  }

  function openEditModal(project) {
    setFormModal({ open: true, mode: "edit", project });
  }

  function closeFormModal() {
    setFormModal((current) => ({ ...current, open: false }));
  }

  async function handleFormSubmit(values) {
    if (formModal.mode === "edit") {
      await updateProject(formModal.project.id, values);
      showToast("Project updated successfully.");
    } else {
      await createProject(values);
      showToast("Project created successfully.");
    }

    closeFormModal();
    await fetchProjects();
  }

  function openArchiveModal(project) {
    setArchiveModal({ open: true, project, submitting: false, error: "" });
  }

  function closeArchiveModal() {
    setArchiveModal({ open: false, project: null, submitting: false, error: "" });
  }

  async function handleArchiveConfirm() {
    setArchiveModal((current) => ({ ...current, submitting: true, error: "" }));

    try {
      await archiveProject(archiveModal.project.id);
      showToast("Project archived successfully.");
      closeArchiveModal();
      await fetchProjects();
    } catch (err) {
      if (err.status === 401) {
        await handleSessionExpired();
        return;
      }
      setArchiveModal((current) => ({
        ...current,
        submitting: false,
        error: err.message || "Unable to archive project. Please try again.",
      }));
    }
  }

  function handleOpenProject(project) {
    navigate(`/projects/${project.id}`);
  }

  const isFiltered = Boolean(debouncedSearch.trim()) || statusFilter !== "all";

  return (
    <AppShell active="projects">
      <div className="page-header-row">
        <div>
          <h1>Projects</h1>
          <p className="page-subtitle">Manage and access all your projects</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={openCreateModal}>
          <Plus size={16} /> Create New Project
        </button>
      </div>

      <div className="projects-toolbar">
        <div className="search-input-wrapper">
          <Search size={16} className="search-input-icon" />
          <input
            type="text"
            placeholder="Search projects..."
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </div>

        <label className="status-filter">
          <span>Filter by Status:</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
            <option value="suspended">Suspended</option>
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
            <p>Failed to load projects.</p>
            <button type="button" className="btn btn-secondary" onClick={fetchProjects}>
              Try Again
            </button>
          </div>
        )}

        {!loading && !loadError && projects.length === 0 && (
          <div className="table-state">
            <p>
              {isFiltered
                ? "No projects match your search or filter."
                : "No projects yet. Create your first project to get started."}
            </p>
          </div>
        )}

        {!loading && !loadError && projects.length > 0 && (
          <>
            <ProjectsTable
              projects={projects}
              onOpen={handleOpenProject}
              onEdit={openEditModal}
              onArchive={openArchiveModal}
            />
            <div className="table-footer-row">
              Showing {projects.length} of {projects.length} projects
            </div>
          </>
        )}
      </div>

      <ProjectFormModal
        open={formModal.open}
        mode={formModal.mode}
        initialProject={formModal.project}
        onClose={closeFormModal}
        onSubmit={handleFormSubmit}
        onAuthError={handleSessionExpired}
      />

      <ArchiveConfirmModal
        open={archiveModal.open}
        project={archiveModal.project}
        submitting={archiveModal.submitting}
        error={archiveModal.error}
        onClose={closeArchiveModal}
        onConfirm={handleArchiveConfirm}
      />
    </AppShell>
  );
}

export default ProjectsPage;