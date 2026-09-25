import { useState } from "react";
import {
  Archive,
  MoreVertical,
  Pencil,
  RotateCcw,
} from "lucide-react";

import {
  FloatingPortal,
  autoUpdate,
  flip,
  offset,
  shift,
  useClick,
  useDismiss,
  useFloating,
  useInteractions,
  useRole,
} from "@floating-ui/react";

import StatusBadge from "./StatusBadge";

function formatDate(isoString) {
  if (!isoString) return "—";

  return new Date(isoString).toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}

function ProjectRowMenu({
  project,
  onEdit,
  onArchive,
  onRestore,
}) {
  const [open, setOpen] = useState(false);

  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement: "bottom-end",
    middleware: [
      offset(6),
      flip({ padding: 8 }),
      shift({ padding: 8 }),
    ],
    whileElementsMounted: autoUpdate,
  });

  const click = useClick(context);
  const dismiss = useDismiss(context);
  const role = useRole(context, { role: "menu" });

  const { getReferenceProps, getFloatingProps } =
    useInteractions([click, dismiss, role]);

  const isArchived = project.status === "archived";

  return (
    <div className="row-menu">
      <button
        type="button"
        ref={refs.setReference}
        {...getReferenceProps()}
        className="row-menu-trigger"
        aria-label={`Actions for ${project.name}`}
      >
        <MoreVertical size={18} />
      </button>

      {open && (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            style={floatingStyles}
            className="row-menu-dropdown"
            {...getFloatingProps()}
          >
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onEdit(project);
              }}
            >
              <Pencil size={14} />
              Edit
            </button>

            {isArchived ? (
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onRestore(project);
                }}
              >
                <RotateCcw size={14} />
                Restore
              </button>
            ) : (
              <button
                type="button"
                role="menuitem"
                className="row-menu-danger"
                onClick={() => {
                  setOpen(false);
                  onArchive(project);
                }}
              >
                <Archive size={14} />
                Archive
              </button>
            )}
          </div>
        </FloatingPortal>
      )}
    </div>
  );
}

function ProjectsTable({
  projects,
  onOpen,
  onEdit,
  onArchive,
  onRestore,
}) {
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
                <span
                  className="project-name-icon"
                  aria-hidden="true"
                >
                  {project.name?.charAt(0).toUpperCase() || "P"}
                </span>

                <span className="project-name-text">
                  {project.name}
                </span>
              </div>
            </td>

            <td>{project.project_type || "—"}</td>

            <td>
              <StatusBadge status={project.status} />
            </td>

            <td>{formatDate(project.created_at)}</td>

            <td>{formatDate(project.updated_at)}</td>

            <td className="projects-table-actions">
              <button
                type="button"
                className="btn btn-primary btn-small"
                onClick={() => onOpen(project)}
              >
                Open
              </button>

              <ProjectRowMenu
                project={project}
                onEdit={onEdit}
                onArchive={onArchive}
                onRestore={onRestore}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default ProjectsTable;