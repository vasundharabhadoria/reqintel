import { useEffect, useRef, useState } from "react";
import { Archive, MoreVertical, Pencil } from "lucide-react";

import StatusBadge from "./StatusBadge";

function formatDate(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}

function ProjectRowMenu({ project, onEdit, onArchive }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  return (
    <div className="row-menu" ref={menuRef}>
      <button
        type="button"
        className="row-menu-trigger"
        onClick={() => setOpen((current) => !current)}
        aria-label={`Actions for ${project.name}`}
      >
        <MoreVertical size={18} />
      </button>

      {open && (
        <div className="row-menu-dropdown">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onEdit(project);
            }}
          >
            <Pencil size={14} /> Edit
          </button>
          <button
            type="button"
            className="row-menu-danger"
            onClick={() => {
              setOpen(false);
              onArchive(project);
            }}
          >
            <Archive size={14} /> Archive
          </button>
        </div>
      )}
    </div>
  );
}

function ProjectsTable({ projects, onOpen, onEdit, onArchive }) {
  return (
    <table className="projects-table">
      <thead>
        <tr>
          <th>Project Name</th>
          <th>Type</th>
          <th>Status</th>
          <th>Created On</th>
          <th>Last Updated</th>
          <th aria-label="Actions" />
        </tr>
      </thead>
      <tbody>
        {projects.map((project) => (
          <tr key={project.id}>
            <td>
              <div className="project-name-cell">
                <span className="project-name-icon" aria-hidden="true">
                  {project.name?.charAt(0).toUpperCase() || "P"}
                </span>
                <span className="project-name-text">{project.name}</span>
              </div>
            </td>
            <td>{project.project_type || "—"}</td>
            <td>
              <StatusBadge status={project.status} />
            </td>
            <td>{formatDate(project.created_at)}</td>
            <td>{formatDate(project.updated_at)}</td>
            <td className="projects-table-actions">
              <button type="button" className="btn btn-primary btn-small" onClick={() => onOpen(project)}>
                Open
              </button>
              <ProjectRowMenu project={project} onEdit={onEdit} onArchive={onArchive} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default ProjectsTable;