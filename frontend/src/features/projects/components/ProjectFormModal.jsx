import { useEffect, useState } from "react";
import { Building2, FileText, Layers, Type } from "lucide-react";

import Modal from "../../../components/common/Modal";

const PROJECT_TYPE_SUGGESTIONS = [
  "Healthcare",
  "Fintech",
  "E-commerce",
  "Telecom",
  "Finance",
  "Human Resources",
];

const EMPTY_FORM = {
  name: "",
  clientName: "",
  projectType: "",
  description: "",
};

function ProjectFormModal({ open, mode, initialProject, onClose, onSubmit, onAuthError }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (!open) return;

    if (mode === "edit" && initialProject) {
      setForm({
        name: initialProject.name || "",
        clientName: initialProject.client_name || "",
        projectType: initialProject.project_type || "",
        description: initialProject.description || "",
      });
    } else {
      setForm(EMPTY_FORM);
    }

    setErrors({});
    setSubmitError("");
  }, [open, mode, initialProject]);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function validate() {
    const nextErrors = {};

    if (!form.name.trim()) {
      nextErrors.name = "Project name is required.";
    } else if (form.name.trim().length > 200) {
      nextErrors.name = "Project name must be 200 characters or fewer.";
    }

    if (form.clientName.trim().length > 200) {
      nextErrors.clientName = "Client name must be 200 characters or fewer.";
    }

    if (form.projectType.trim().length > 100) {
      nextErrors.projectType = "Project type must be 100 characters or fewer.";
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitError("");

    if (!validate()) return;

    setSubmitting(true);

    try {
      await onSubmit({
        name: form.name.trim(),
        clientName: form.clientName.trim() || null,
        projectType: form.projectType.trim() || null,
        description: form.description.trim() || null,
      });
    } catch (err) {
      if (err.status === 401 && onAuthError) {
        onAuthError();
        return;
      }
      setSubmitError(err.message || "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const isEdit = mode === "edit";

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? "Edit Project" : "Create New Project"}>
      <p className="project-modal-subtitle">
        {isEdit
          ? "Update the project details below."
          : "Set up a new workspace for your requirements."}
      </p>

      {submitError && <div className="project-form-error">{submitError}</div>}

      <form onSubmit={handleSubmit} noValidate className="project-form">
        <div className="project-form-field">
          <label htmlFor="project-name">
            Project Name <span className="required-mark">*</span>
          </label>
          <div className="project-form-input-wrapper">
            <Type size={16} className="project-form-input-icon" />
            <input
              id="project-name"
              type="text"
              placeholder="e.g., Telecom Billing System"
              value={form.name}
              onChange={(event) => updateField("name", event.target.value)}
              maxLength={200}
            />
          </div>
          {errors.name && <span className="field-error">{errors.name}</span>}
        </div>

        <div className="project-form-field">
          <label htmlFor="project-client">Client Name</label>
          <div className="project-form-input-wrapper">
            <Building2 size={16} className="project-form-input-icon" />
            <input
              id="project-client"
              type="text"
              placeholder="e.g., Quantum Telecom Inc."
              value={form.clientName}
              onChange={(event) => updateField("clientName", event.target.value)}
              maxLength={200}
            />
          </div>
          {errors.clientName && <span className="field-error">{errors.clientName}</span>}
        </div>

        <div className="project-form-field">
          <label htmlFor="project-type">Project Type</label>
          <div className="project-form-input-wrapper">
            <Layers size={16} className="project-form-input-icon" />
            <input
              id="project-type"
              type="text"
              list="project-type-suggestions"
              placeholder="e.g., Telecom"
              value={form.projectType}
              onChange={(event) => updateField("projectType", event.target.value)}
              maxLength={100}
            />
          </div>
          <datalist id="project-type-suggestions">
            {PROJECT_TYPE_SUGGESTIONS.map((suggestion) => (
              <option key={suggestion} value={suggestion} />
            ))}
          </datalist>
          {errors.projectType && <span className="field-error">{errors.projectType}</span>}
        </div>

        <div className="project-form-field">
          <label htmlFor="project-description">Description</label>
          <div className="project-form-input-wrapper project-form-textarea-wrapper">
            <FileText size={16} className="project-form-input-icon" />
            <textarea
              id="project-description"
              placeholder="Describe the project's goals and core features."
              value={form.description}
              onChange={(event) => updateField("description", event.target.value)}
              rows={3}
            />
          </div>
        </div>

        <div className="project-form-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting
              ? isEdit
                ? "Saving..."
                : "Creating..."
              : isEdit
              ? "Apply Changes"
              : "Create Project"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default ProjectFormModal;