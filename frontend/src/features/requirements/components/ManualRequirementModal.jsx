import { useState } from "react";

import Modal from "../../../components/common/Modal";
import { createManualRequirement } from "../../../api/requirementsApi";
import { useToast } from "../../../hooks/useToast";

function ManualRequirementModal({ open, onClose, projectId, onCreated }) {
  const { showToast } = useToast();
  const [title, setTitle] = useState("");
  const [requirementText, setRequirementText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function reset() {
    setTitle("");
    setRequirementText("");
    setError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (!title.trim() || !requirementText.trim()) {
      setError("Title and requirement text are both required.");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createManualRequirement(projectId, {
        title: title.trim(),
        requirementText: requirementText.trim(),
      });
      showToast(`${created.requirement_code} created.`, "success");
      reset();
      onCreated(created);
      onClose();
    } catch (err) {
      setError(err.message || "Failed to create the requirement.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Add Requirement Manually"
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" form="manual-req-form" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Saving…" : "Save Requirement"}
          </button>
        </>
      }
    >
      <form id="manual-req-form" onSubmit={handleSubmit}>
        {error && <p className="form-error">{error}</p>}

        <label className="form-field">
          <span>Title</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={255}
            disabled={submitting}
          />
        </label>

        <label className="form-field">
          <span>Requirement Text</span>
          <textarea
            rows={5}
            value={requirementText}
            onChange={(e) => setRequirementText(e.target.value)}
            disabled={submitting}
          />
        </label>
      </form>
    </Modal>
  );
}

export default ManualRequirementModal;