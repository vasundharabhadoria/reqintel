import { AlertTriangle, Archive } from "lucide-react";

import Modal from "../../../components/common/Modal";

function ArchiveConfirmModal({ open, project, submitting, error, onClose, onConfirm }) {
  return (
    <Modal open={open} onClose={onClose} title="Archive Project?" icon={<Archive size={20} />} size="sm">
      <p className="archive-modal-text">
        Are you sure you want to archive the project{" "}
        <strong>&ldquo;{project?.name}&rdquo;</strong>?
      </p>

      <div className="archive-modal-warning">
        <AlertTriangle size={16} />
        <span>
          Archived projects are hidden from the active list but not deleted — you can still
          find them anytime using the Archived status filter.
        </span>
      </div>

      {error && <div className="project-form-error">{error}</div>}

      <div className="project-form-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={submitting}>
          {submitting ? "Archiving..." : "Archive"}
        </button>
      </div>
    </Modal>
  );
}

export default ArchiveConfirmModal;