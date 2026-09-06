import { useState } from "react";
import {
  X,
  ChevronDown,
  CheckCircle2,
  AlertTriangle,
  FileText,
  ExternalLink,
} from "lucide-react";
import StatusPill from "../../requirements/components/StatusPill";

function RuleDetailsModal({ requirement, onClose }) {
  const [expandedFinding, setExpandedFinding] = useState(null);

  const findings = requirement.findings || [];

  const sourceDocument =
    requirement.source_document_name || "—";

  const sourceDocumentUrl =
    requirement.source_document_url || null;

  const getFileExtension = (filename) => {
    if (!filename || filename === "—") return "";

    const parts = filename.split(".");

    return parts.length > 1
      ? parts[parts.length - 1].toLowerCase()
      : "";
  };

  const fileExtension =
    getFileExtension(sourceDocument);

  const getFileTypeLabel = () => {
    switch (fileExtension) {
      case "pdf":
        return "PDF";

      case "doc":
      case "docx":
        return "Word";

      case "txt":
        return "Text";

      case "xls":
      case "xlsx":
        return "Excel";

      case "ppt":
      case "pptx":
        return "PowerPoint";

      default:
        return fileExtension
          ? fileExtension.toUpperCase()
          : "Document";
    }
  };

  const openSourceDocument = () => {
    if (!sourceDocumentUrl) {
      console.warn(
        "No source document URL available:",
        requirement
      );

      return;
    }

    window.open(
      sourceDocumentUrl,
      "_blank",
      "noopener,noreferrer"
    );
  };

  const toggleFinding = (index) => {
    setExpandedFinding((current) =>
      current === index ? null : index
    );
  };

  return (
    <div
      className="rule-drawer-overlay"
      onClick={onClose}
    >
      <aside
        className="rule-drawer"
        onClick={(event) =>
          event.stopPropagation()
        }
      >
        {/* DRAWER HEADER */}

        <div className="rule-drawer-header">
          <div className="rule-drawer-title-area">
            <h2>Requirement Details</h2>
          </div>

          <button
            type="button"
            className="rule-drawer-close"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={22} />
          </button>
        </div>

        <div className="rule-drawer-body">

          {/* REQUIREMENT ID + STATUS */}

          <div className="rule-drawer-requirement-top">
            <span className="rule-drawer-code">
              {requirement.requirement_code}
            </span>

            <StatusPill
              status={
                requirement.status || "pending"
              }
            />
          </div>

          {/* SOURCE DOCUMENT */}

          <section className="rule-drawer-section rule-source-section">
            <h3>Source Document</h3>

            <button
              type="button"
              className={`rule-drawer-source-document ${
                sourceDocumentUrl
                  ? "clickable"
                  : "disabled"
              }`}
              onClick={openSourceDocument}
              disabled={!sourceDocumentUrl}
              title={
                sourceDocumentUrl
                  ? "Open source document"
                  : "Source document URL is not available"
              }
            >
              <div className="rule-drawer-source-info">

                <div
                  className={`rule-drawer-file-icon file-${fileExtension}`}
                >
                  <FileText size={19} />
                </div>

                <div className="rule-drawer-file-details">

                  <span className="rule-drawer-file-name">
                    {sourceDocument}
                  </span>

                  <span className="rule-drawer-file-type">
                    {getFileTypeLabel()}
                  </span>

                </div>

                {sourceDocumentUrl && (
                  <ExternalLink
                    size={17}
                    className="rule-drawer-source-open-icon"
                  />
                )}

              </div>
            </button>
          </section>

          {/* REQUIREMENT */}

          <section className="rule-drawer-section">
            <h3>Requirement</h3>

            <p>
              {requirement.current_requirement_text ||
                "No requirement text available."}
            </p>
          </section>

          {/* RULE ENGINE FINDINGS */}

          <section className="rule-drawer-section">
            <div className="rule-findings-heading">
              <div>
                <h3>Rule Engine Findings</h3>

                <p>
                  {findings.length} checks evaluated
                </p>
              </div>
            </div>

            <div className="rule-findings-list">

              {findings.length === 0 && (
                <div className="rule-no-findings">
                  No rule engine findings available.
                </div>
              )}

              {findings.map((finding, index) => {
                const isExpanded =
                  expandedFinding === index;

                const passed =
                  finding.passed === true;

                return (
                  <div
                    className={`rule-finding ${
                      passed
                        ? "passed"
                        : "failed"
                    }`}
                    key={`${finding.rule_name}-${index}`}
                  >
                    <button
                      type="button"
                      className="rule-finding-header"
                      onClick={() =>
                        toggleFinding(index)
                      }
                    >
                      <div className="rule-finding-title">

                        {passed ? (
                          <CheckCircle2 size={18} />
                        ) : (
                          <AlertTriangle size={18} />
                        )}

                        <span>
                          {finding.rule_name}
                        </span>

                      </div>

                      <ChevronDown
                        size={18}
                        className={
                          isExpanded
                            ? "finding-chevron expanded"
                            : "finding-chevron"
                        }
                      />
                    </button>

                    {isExpanded && (
                      <div className="rule-finding-content">

                        <div className="finding-detail">
                          <span>Status</span>

                          <strong>
                            {passed
                              ? "Passed"
                              : "Failed"}
                          </strong>
                        </div>

                        <div className="finding-detail">
                          <span>Description</span>

                          <p>
                            {finding.description ||
                              finding.message ||
                              "No description available."}
                          </p>
                        </div>

                        <div className="finding-detail">
                          <span>Why it matters</span>

                          <p>
                            {finding.why_it_matters ||
                              "No additional information available."}
                          </p>
                        </div>

                        <div className="finding-detail">
                          <span>Recommendation</span>

                          <p>
                            {finding.recommendation ||
                              "No recommendation available."}
                          </p>
                        </div>

                      </div>
                    )}
                  </div>
                );
              })}

            </div>
          </section>

        </div>
      </aside>
    </div>
  );
}

export default RuleDetailsModal;