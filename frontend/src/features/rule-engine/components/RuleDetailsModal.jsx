import { useState } from "react";
import {
  X,
  ChevronDown,
  CheckCircle2,
  AlertTriangle,
  FileText,
  ExternalLink,
  Copy,
  Check,
  Sparkles,
} from "lucide-react";
import StatusPill from "../../requirements/components/StatusPill";

function RuleDetailsModal({ requirement, onClose }) {
  const [expandedFinding, setExpandedFinding] = useState(null);
  const [copied, setCopied] = useState(false);

  const findings = Array.isArray(requirement?.findings)
    ? requirement.findings
    : [];

  const sourceDocument =
    requirement?.source_document_name || "—";

  const sourceDocumentUrl =
    requirement?.source_document_url || null;

  const requirementText =
    requirement?.current_requirement_text ||
    requirement?.requirement_text ||
    requirement?.text ||
    "—";

  const getFileExtension = (filename = "") => {
    if (!filename || typeof filename !== "string") {
      return "";
    }

    const parts = filename.split(".");

    if (parts.length < 2) {
      return "";
    }

    return parts[parts.length - 1].toUpperCase();
  };

  const getFileTypeLabel = () => {
    const extension = getFileExtension(sourceDocument);

    if (!extension) {
      return "";
    }

    return extension;
  };

  const openSourceDocument = () => {
    if (!sourceDocumentUrl) {
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

  const copyRequirement = async () => {
    if (!requirementText || requirementText === "—") {
      return;
    }

    try {
      await navigator.clipboard.writeText(requirementText);

      setCopied(true);

      setTimeout(() => {
        setCopied(false);
      }, 1500);
    } catch {
      setCopied(false);
    }
  };

  const getSeverityClass = (severity) => {
    const value = String(severity || "Low").toLowerCase();

    if (value === "high") {
      return "rule-severity high";
    }

    if (value === "medium") {
      return "rule-severity medium";
    }

    return "rule-severity low";
  };

  const getFindingSeverity = (finding) => {
    if (finding?.severity) {
      return finding.severity;
    }

    const matchedRules =
      finding?.matched_rules ||
      finding?.rules ||
      [];

    if (!matchedRules.length) {
      return finding?.passed ? "Low" : "High";
    }

    const severities = matchedRules.map(
      (rule) =>
        String(rule?.severity || "Low").toLowerCase()
    );

    if (severities.includes("high")) {
      return "High";
    }

    if (severities.includes("medium")) {
      return "Medium";
    }

    return "Low";
  };

  const getMatchedRules = (finding) => {
    const rules =
      finding?.matched_rules ||
      finding?.rules ||
      [];

    if (!Array.isArray(rules)) {
      return [];
    }

    return rules;
  };

  const getFindingTitle = (finding) => {
    return (
      finding?.category ||
      finding?.rule_name ||
      "Rule Check"
    );
  };

  const getFindingDescription = (finding) => {
    return (
      finding?.description ||
      finding?.message ||
      "No description available."
    );
  };

  const getFindingWhyItMatters = (finding) => {
    return (
      finding?.why_it_matters ||
      finding?.whyItMatters ||
      "No additional information available."
    );
  };

  const getFindingRecommendation = (finding) => {
    return (
      finding?.recommendation ||
      "No recommendation is available."
    );
  };

  const getRuleName = (rule) => {
    if (typeof rule === "string") {
      return rule;
    }

    return (
      rule?.rule_name ||
      rule?.rule ||
      rule?.name ||
      "Configured rule"
    );
  };

  const getRuleDescription = (rule) => {
    return (
      rule?.description ||
      "This rule matched the requirement."
    );
  };

  const getRuleWhyItMatters = (rule) => {
    return (
      rule?.why_it_matters ||
      rule?.whyItMatters ||
      ""
    );
  };

  const getRuleRecommendation = (rule) => {
    return (
      rule?.recommendation ||
      ""
    );
  };

  const getRuleSeverity = (rule) => {
    return rule?.severity || "Low";
  };

  const aiSuggestions = findings.filter(
    (finding) =>
      finding?.type === "suggestion" ||
      finding?.category === "suggestion" ||
      finding?.ai_suggestion === true
  );

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
        {/* HEADER */}

        <header className="rule-drawer-header">
          <div>
            <h2>Requirement Details</h2>

            <p>
              Review requirement validation findings
            </p>
          </div>

          <button
            type="button"
            className="rule-drawer-close"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={21} />
          </button>
        </header>

        {/* SCROLLABLE CONTENT */}

        <div className="rule-drawer-content">

          {/* REQUIREMENT META */}

         <section className="requirement-meta">
  <strong className="requirement-meta-id">
    {requirement?.requirement_code ||
      requirement?.code ||
      "—"}
  </strong>

  <span
    className={`requirement-status-badge ${
      String(requirement?.status || "pending")
        .toLowerCase()
        .replace(/\s+/g, "-")
    }`}
  >
    {String(requirement?.status || "pending").toLowerCase() === "pending"
      ? "Pending Review"
      : requirement?.status || "Pending Review"}
  </span>
</section>

          {/* SOURCE DOCUMENT */}

          <section className="drawer-section">
            <div className="drawer-section-title">
              <FileText size={17} />

              <span>Source Document</span>
            </div>

            <div className="source-document-card">
              <div className="source-document-info">
                <div className="source-file-icon">
                  <FileText size={18} />
                </div>

                <div className="source-file-name">
                  <strong>
                    {sourceDocument}
                  </strong>

                  {getFileTypeLabel() && (
                    <span>
                      {getFileTypeLabel()}
                    </span>
                  )}
                </div>
              </div>

              {sourceDocumentUrl && (
                <button
                  type="button"
                  className="source-open-button"
                  onClick={openSourceDocument}
                >
                  <span>Open</span>
                  <ExternalLink size={15} />
                </button>
              )}
            </div>
          </section>

          {/* REQUIREMENT */}

          <section className="drawer-section">
            <div className="drawer-section-title requirement-title">
              <FileText size={17} />

              <span>Requirement</span>
            </div>

            <div className="requirement-text-card">
              <p>{requirementText}</p>

              <button
                type="button"
                className="copy-requirement-button"
                onClick={copyRequirement}
                title="Copy requirement"
              >
                {copied ? (
                  <Check size={17} />
                ) : (
                  <Copy size={17} />
                )}
              </button>
            </div>
          </section>

          {/* RULE ENGINE FINDINGS */}

          <section className="drawer-section findings-section">
            <div className="findings-heading">
              <div>
                <h3>Rule Engine Findings</h3>

                <p>
                  {findings.length}{" "}
                  {findings.length === 1
                    ? "validation check"
                    : "validation checks"}{" "}
                  displayed
                </p>
              </div>

              <span className="findings-count">
                {findings.length} Checks
              </span>
            </div>

            <div className="findings-list">

              {findings.length === 0 && (
                <div className="no-findings">
                  No validation findings are available.
                </div>
              )}

              {findings.map(
                (finding, index) => {
                  const passed =
                    finding?.passed !== false;

                  const expanded =
                    expandedFinding === index;

                  const matchedRules =
                    getMatchedRules(finding);

                  const severity =
                    getFindingSeverity(finding);

                  return (
                    <article
                      key={`${getFindingTitle(
                        finding
                      )}-${index}`}
                      className={`rule-finding ${
                        passed
                          ? "passed"
                          : "failed"
                      }`}
                    >
                      <button
                        type="button"
                        className="rule-finding-header"
                        onClick={() =>
                          toggleFinding(index)
                        }
                      >
                        <div className="finding-title-group">

                          <span
                            className={`finding-status-icon ${
                              passed
                                ? "success"
                                : "error"
                            }`}
                          >
                            {passed ? (
                              <CheckCircle2
                                size={18}
                              />
                            ) : (
                              <AlertTriangle
                                size={18}
                              />
                            )}
                          </span>

                          <span className="finding-title">
                            {getFindingTitle(
                              finding
                            )}
                          </span>

                          <span
                            className={getSeverityClass(
                              severity
                            )}
                          >
                            {severity}
                          </span>
                        </div>

                        <ChevronDown
                          size={18}
                          className={
                            expanded
                              ? "finding-chevron open"
                              : "finding-chevron"
                          }
                        />
                      </button>

                      {expanded && (
                        <div className="rule-finding-body">

                          <div className="finding-row">
                            <span className="finding-label">
                              Status
                            </span>

                            <span
                              className={`finding-status ${
                                passed
                                  ? "passed"
                                  : "failed"
                              }`}
                            >
                              {passed
                                ? "Passed"
                                : "Failed"}
                            </span>
                          </div>

                          {/* MATCHED RULES */}

                          {matchedRules.length >
                            0 && (
                            <div className="matched-rules-section">
                              <span className="finding-label">
                                Matched Rules
                              </span>

                              <div className="matched-rules-list">
                                {matchedRules.map(
                                  (
                                    rule,
                                    ruleIndex
                                  ) => (
                                    <div
                                      className="matched-rule-card"
                                      key={`${getRuleName(
                                        rule
                                      )}-${ruleIndex}`}
                                    >
                                      <div className="matched-rule-top">
                                        <div className="matched-rule-name">
                                          <span className="matched-rule-dot" />

                                          <strong>
                                            {getRuleName(
                                              rule
                                            )}
                                          </strong>
                                        </div>

                                        <span
                                          className={getSeverityClass(
                                            getRuleSeverity(
                                              rule
                                            )
                                          )}
                                        >
                                          {getRuleSeverity(
                                            rule
                                          )}
                                        </span>
                                      </div>

                                      {getRuleDescription(
                                        rule
                                      ) && (
                                        <p>
                                          {
                                            getRuleDescription(
                                              rule
                                            )
                                          }
                                        </p>
                                      )}

                                      {getRuleWhyItMatters(
                                        rule
                                      ) && (
                                        <div className="matched-rule-detail">
                                          <span>
                                            Why it matters
                                          </span>

                                          <p>
                                            {
                                              getRuleWhyItMatters(
                                                rule
                                              )
                                            }
                                          </p>
                                        </div>
                                      )}

                                      {getRuleRecommendation(
                                        rule
                                      ) && (
                                        <div className="matched-rule-detail">
                                          <span>
                                            Recommendation
                                          </span>

                                          <p>
                                            {
                                              getRuleRecommendation(
                                                rule
                                              )
                                            }
                                          </p>
                                        </div>
                                      )}
                                    </div>
                                  )
                                )}
                              </div>
                            </div>
                          )}

                          {/* CATEGORY DESCRIPTION */}

                          <div className="finding-detail">
                            <span className="finding-label">
                              Description
                            </span>

                            <p>
                              {getFindingDescription(
                                finding
                              )}
                            </p>
                          </div>

                          <div className="finding-detail">
                            <span className="finding-label">
                              Why it matters
                            </span>

                            <p>
                              {getFindingWhyItMatters(
                                finding
                              )}
                            </p>
                          </div>

                          <div className="finding-detail">
                            <span className="finding-label">
                              Recommendation
                            </span>

                            <p>
                              {getFindingRecommendation(
                                finding
                              )}
                            </p>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                }
              )}
            </div>
          </section>

          {/* AI SUGGESTIONS */}

          {aiSuggestions.length > 0 && (
            <section className="drawer-section ai-suggestions-section">

              <div className="findings-heading">
                <div>
                  <div className="ai-heading">
                    <Sparkles size={17} />

                    <h3>
                      AI Suggestions
                    </h3>
                  </div>
                </div>

                <span className="findings-count">
                  {aiSuggestions.length}{" "}
                  {aiSuggestions.length === 1
                    ? "Suggestion"
                    : "Suggestions"}
                </span>
              </div>

              <div className="ai-suggestions-list">
                {aiSuggestions.map(
                  (suggestion, index) => (
                    <div
                      className="ai-suggestion-card"
                      key={index}
                    >
                      <div className="ai-suggestion-icon">
                        <Sparkles size={17} />
                      </div>

                      <div className="ai-suggestion-content">
                        <p>
                          {suggestion.message ||
                            suggestion.description ||
                            suggestion.suggestion ||
                            "AI recommendation available."}
                        </p>

                        <div className="ai-suggestion-actions">
                          <button
                            type="button"
                            className="suggestion-accept"
                          >
                            <ThumbsUp size={14} />
                            Accept
                          </button>

                          <button
                            type="button"
                            className="suggestion-reject"
                          >
                            <ThumbsDown size={14} />
                            Reject
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                )}
              </div>
            </section>
          )}
        </div>

      </aside>
    </div>
  );
}

export default RuleDetailsModal;