import { useState } from "react";

import Modal from "../../../components/common/Modal";
import { createEmailSource } from "../../../api/requirementsApi";
import { useToast } from "../../../hooks/useToast";

function EmailSourceModal({ open, onClose, projectId, onCreated }) {
  const { showToast } = useToast();
  const [subject, setSubject] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function reset() {
    setSubject("");
    setContent("");
    setError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (!content.trim()) {
      setError("Paste the email content before saving.");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createEmailSource(projectId, {
        subject: subject.trim(),
        content: content.trim(),
      });
      showToast("Email content saved as a source. Run \u201cExtract Requirements\u201d to identify requirements from it.", "success");
      reset();
      onCreated(created);
      onClose();
    } catch (err) {
      setError(err.message || "Failed to save the email content.");
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
      title="Add Email Content"
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" form="email-source-form" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Saving…" : "Save Source"}
          </button>
        </>
      }
    >
      <form id="email-source-form" onSubmit={handleSubmit}>
        {error && <p className="form-error">{error}</p>}

        <label className="form-field">
          <span>Subject (optional)</span>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            maxLength={255}
            disabled={submitting}
          />
        </label>

        <label className="form-field">
          <span>Email Content</span>
          <textarea
            rows={8}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={submitting}
            placeholder="Paste the email body here…"
          />
        </label>
      </form>
    </Modal>
  );
}

export default EmailSourceModal;