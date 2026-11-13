import { AlertTriangle, Trash2 } from "lucide-react";

import Modal from "../../../components/common/Modal";

function DeleteReportModal({ open, report, submitting, error, onClose, onConfirm }) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Delete Report?"
      icon={<Trash2 size={20} />}
      size="sm"
    >
      <p className="archive-modal-text">
        Are you sure you want to delete{" "}
        <strong>&ldquo;{report?.file_name}&rdquo;</strong>?
      </p>

      <div className="archive-modal-warning">
        <AlertTriangle size={16} />
        <span>
          The generated file will be permanently removed. You can generate a
          new report for the project at any time.
        </span>
      </div>

      {error && <div className="project-form-error">{error}</div>}

      <div className="project-form-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-danger"
          onClick={onConfirm}
          disabled={submitting}
        >
          {submitting ? "Deleting..." : "Delete"}
        </button>
      </div>
    </Modal>
  );
}

export default DeleteReportModal;