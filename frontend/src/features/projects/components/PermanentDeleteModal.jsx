import { useState } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";

import Modal from "../../../components/common/Modal";

const DELETED_ITEMS = [
  "Project information",
  "Uploaded requirement documents",
  "Extracted requirements and their versions",
  "Repository versions and snapshots",
  "Validation results",
  "AI analysis and suggestions",
  "Traceability relationships",
  "Change impact records",
  "Associated reports and generated files",
];

function PermanentDeleteModal({
  open,
  project,
  submitting,
  error,
  onClose,
  onConfirm,
}) {
  const [typedName, setTypedName] = useState("");

  // The parent mounts this modal only while it is open, so the typed name
  // always starts empty and a previous confirmation can never carry over.

  if (!project) return null;

  const matches = typedName === project.name;
  const canDelete = matches && !submitting;

  function handleClose() {
    if (!submitting) onClose();
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && canDelete) onConfirm();
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Permanently Delete Project?"
      icon={<AlertTriangle size={20} color="#b91c1c" />}
      footer={
        <>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleClose}
            disabled={submitting}
          >
            Cancel
          </button>

          <button
            type="button"
            className="btn btn-danger"
            onClick={onConfirm}
            disabled={!canDelete}
          >
            {submitting ? (
              "Deleting..."
            ) : (
              <>
                <Trash2 size={14} />
                Permanently Delete
              </>
            )}
          </button>
        </>
      }
    >
      {error && <div className="project-form-error">{error}</div>}

      <div className="permanent-delete-warning">
        <AlertTriangle size={16} />
        <span>
          This action <strong>cannot be undone</strong>. Unlike archiving, the
          project cannot be restored afterwards.
        </span>
      </div>

      <p className="archive-modal-text">
        You are about to permanently delete <strong>{project.name}</strong>.
        The following will be removed:
      </p>

      <ul className="permanent-delete-list">
        {DELETED_ITEMS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <label
        className="permanent-delete-confirm-label"
        htmlFor="permanent-delete-confirm"
      >
        Type <strong>{project.name}</strong> to confirm
      </label>

      <input
        id="permanent-delete-confirm"
        className="permanent-delete-confirm-input"
        type="text"
        autoComplete="off"
        autoFocus
        value={typedName}
        onChange={(event) => setTypedName(event.target.value)}
        onKeyDown={handleKeyDown}
        disabled={submitting}
        placeholder={project.name}
      />
    </Modal>
  );
}

export default PermanentDeleteModal;
