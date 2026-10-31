import { useEffect, useState } from "react";
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
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";

function RuleDetailsModal({
  requirement,
  onClose,
  onAcceptSuggestion,
  onRejectSuggestion,
  onReviewComplete,
  onWaiveFinding,
}) {
  const [waiveBusy, setWaiveBusy] = useState(false);

  const [expandedFinding, setExpandedFinding] =
    useState(null);

  const [copied, setCopied] = useState(false);

  const findings = Array.isArray(
    requirement?.findings
  )
    ? requirement.findings
    : [];

  const sourceDocument =
    requirement?.source_document_name || "—";

  const sourceDocumentUrl =
    requirement?.source_document_url || null;

  const requirementText =
    requirement?.draft_requirement_text ||
    requirement?.current_requirement_text ||
    requirement?.requirement_text ||
    requirement?.text ||
    "—";

  const getFileExtension = (filename = "") => {
    if (
      !filename ||
      typeof filename !== "string"
    ) {
      return "";
    }

    const parts = filename.split(".");

    if (parts.length < 2) {
      return "";
    }

    return parts[
      parts.length - 1
    ].toUpperCase();
  };

  const getFileTypeLabel = () => {
    const extension =
      getFileExtension(
        sourceDocument
      );

    return extension || "";
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
    setExpandedFinding(
      (current) =>
        current === index
          ? null
          : index
    );
  };

  const copyRequirement =
    async () => {
      if (
        !requirementText ||
        requirementText === "—"
      ) {
        return;
      }

      try {
        await navigator.clipboard.writeText(
          requirementText
        );

        setCopied(true);

        setTimeout(() => {
          setCopied(false);
        }, 1500);
      } catch {
        setCopied(false);
      }
    };

  const getSeverityClass = (
    severity
  ) => {
    const value = String(
      severity || "Low"
    ).toLowerCase();

    if (value === "high") {
      return "rule-severity high";
    }

    if (value === "medium") {
      return "rule-severity medium";
    }

    return "rule-severity low";
  };

  const getFindingSeverity = (
    finding
  ) => {
    if (finding?.severity) {
      return finding.severity;
    }

    const matchedRules =
      finding?.matched_rules ||
      finding?.rules ||
      [];

    if (!matchedRules.length) {
      return finding?.passed
        ? "Low"
        : "High";
    }

    const severities =
      matchedRules.map(
        (rule) =>
          String(
            rule?.severity || "Low"
          ).toLowerCase()
      );

    if (
      severities.includes("high")
    ) {
      return "High";
    }

    if (
      severities.includes("medium")
    ) {
      return "Medium";
    }

    return "Low";
  };

  const getMatchedRules = (
    finding
  ) => {
    const rules =
      finding?.matched_rules ||
      finding?.rules ||
      [];

    return Array.isArray(rules)
      ? rules
      : [];
  };

  const getFindingTitle = (
    finding
  ) => {
    return (
      finding?.category ||
      finding?.rule_name ||
      "Rule Check"
    );
  };

  const getFindingDescription = (
    finding
  ) => {
    return (
      finding?.description ||
      finding?.message ||
      "No description available."
    );
  };

  const getFindingWhyItMatters = (
    finding
  ) => {
    return (
      finding?.why_it_matters ||
      finding?.whyItMatters ||
      "No additional information available."
    );
  };

  const getFindingRecommendation = (
    finding
  ) => {
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

  const getRuleDescription = (
    rule
  ) => {
    return (
      rule?.description ||
      "This rule matched the requirement."
    );
  };

  const getRuleWhyItMatters = (
    rule
  ) => {
    return (
      rule?.why_it_matters ||
      rule?.whyItMatters ||
      ""
    );
  };

  const getRuleRecommendation = (
    rule
  ) => {
    return (
      rule?.recommendation || ""
    );
  };

  const getRuleSeverity = (
    rule
  ) => {
    return rule?.severity || "Low";
  };

  /*
   * -------------------------------------------------------
   * AI SUGGESTIONS
   * -------------------------------------------------------
   */

  const aiSuggestions =
    Array.isArray(
      requirement?.ai_suggestions
    )
      ? requirement.ai_suggestions
      : findings.filter(
          (finding) =>
            finding?.type ===
              "suggestion" ||
            finding?.category ===
              "suggestion" ||
            finding?.ai_suggestion ===
              true
        );

  const parseRawAIResponse = (
    rawResponse
  ) => {
    if (!rawResponse) {
      return null;
    }

    if (
      typeof rawResponse ===
      "object"
    ) {
      return rawResponse;
    }

    if (
      typeof rawResponse ===
      "string"
    ) {
      try {
        return JSON.parse(
          rawResponse
        );
      } catch {
        return null;
      }
    }

    return null;
  };

  const parsedRawAIResponse =
    parseRawAIResponse(
      requirement?.ai_analysis
        ?.raw_response_json
    );

  const qualityAssessment =
    requirement?.ai_quality_assessment ||
    parsedRawAIResponse
      ?.quality_assessment ||
    null;

  /*
   * -------------------------------------------------------
   * QUALITY SCORE
   * -------------------------------------------------------
   */

  const normalizeQualityValue = (
    value
  ) => {
    const rawValue = String(
      value || ""
    )
      .trim()
      .toLowerCase();

    if (!rawValue) {
      return "";
    }

    const match =
      rawValue.match(
        /^(high|good|clear|complete|consistent|medium|moderate|low|poor|incomplete|inconsistent|ambiguous)\b/i
      );

    if (!match) {
      return "";
    }

    const level =
      match[1].toLowerCase();

    if (
      level === "high" ||
      level === "good" ||
      level === "clear" ||
      level === "complete" ||
      level === "consistent"
    ) {
      return "high";
    }

    if (
      level === "medium" ||
      level === "moderate"
    ) {
      return "medium";
    }

    if (
      level === "low" ||
      level === "poor" ||
      level === "incomplete" ||
      level === "inconsistent" ||
      level === "ambiguous"
    ) {
      return "low";
    }

    return "";
  };

  const calculateQualityScore = (
    assessment
  ) => {
    if (
      !assessment ||
      typeof assessment !==
        "object"
    ) {
      return null;
    }

    const getScore = (
      key,
      highScore,
      mediumScore,
      lowScore
    ) => {
      const level =
        normalizeQualityValue(
          assessment?.[key]
        );

      if (level === "high") {
        return highScore;
      }

      if (level === "medium") {
        return mediumScore;
      }

      if (level === "low") {
        return lowScore;
      }

      return 0;
    };

    const total =
      getScore(
        "clarity",
        17,
        12,
        6
      ) +
      getScore(
        "completeness",
        17,
        12,
        6
      ) +
      getScore(
        "unambiguity",
        15,
        10,
        5
      ) +
      getScore(
        "consistency",
        17,
        12,
        6
      ) +
      getScore(
        "specificity",
        17,
        12,
        6
      ) +
      getScore(
        "testability",
        17,
        12,
        6
      );

    return Math.max(
      0,
      Math.min(
        100,
        Math.round(total)
      )
    );
  };

  const calculatedQualityScore =
    calculateQualityScore(
      qualityAssessment
    );

  const qualityScore =
    requirement?.quality_score !==
      null &&
    requirement?.quality_score !==
      undefined &&
    Number.isFinite(
      Number(
        requirement?.quality_score
      )
    )
      ? Number(
          requirement.quality_score
        )
      : calculatedQualityScore ??
        requirement?.final_quality_score ??
        requirement?.qualityScore ??
        null;

  const qualityDimensions = [
    {
      key: "clarity",
      label: "Clarity",
    },
    {
      key: "completeness",
      label: "Completeness",
    },
    {
      key: "unambiguity",
      label: "Unambiguity",
    },
    {
      key: "consistency",
      label: "Consistency",
    },
    {
      key: "specificity",
      label: "Specificity",
    },
    {
      key: "testability",
      label: "Testability",
    },
  ];

  const getQualityDimensionStatus =
    (value) => {
      const level =
        normalizeQualityValue(
          value
        );

      if (level === "high") {
        return "Good";
      }

      if (level === "medium") {
        return "Moderate";
      }

      if (level === "low") {
        return "Needs improvement";
      }

      return "Not assessed";
    };

  const getQualityDimensionClass =
    (value) => {
      const level =
        normalizeQualityValue(
          value
        );

      if (level === "high") {
        return "good";
      }

      if (level === "medium") {
        return "moderate";
      }

      if (level === "low") {
        return "needs-improvement";
      }

      return "moderate";
    };

  const getQualityDimensionProgress =
    (value) => {
      const level =
        normalizeQualityValue(
          value
        );

      if (level === "high") {
        return 100;
      }

      if (level === "medium") {
        return 65;
      }

      if (level === "low") {
        return 35;
      }

      return 0;
    };

  /*
   * -------------------------------------------------------
   * LOCAL REVIEW STATE
   * -------------------------------------------------------
   */

  const [
    localSuggestions,
    setLocalSuggestions,
  ] = useState(() =>
    aiSuggestions.map(
      (suggestion) => ({
        ...suggestion,
      })
    )
  );

  const [reviewedDecision, setReviewedDecision] =
    useState(null);

  useEffect(() => {
    /*
     * Reset review state only when a different requirement is opened.
     * Parent Accept/Reject updates must not reset the local review
     * decision while the drawer is still open.
     */
    setLocalSuggestions(
      aiSuggestions.map(
        (suggestion) => ({
          ...suggestion,
        })
      )
    );
    setReviewedDecision(null);
  }, [requirement?.id]);

  const getSuggestionStatus =
    (suggestion) =>
      String(
        suggestion?.status ||
          "pending"
      ).toLowerCase();

  const updateLocalSuggestion = (
    suggestion,
    status
  ) => {
    setLocalSuggestions(
      (current) =>
        current.map(
          (item) =>
            String(item?.id) ===
            String(suggestion?.id)
              ? {
                  ...item,
                  status,
                  reviewed_at:
                    new Date().toISOString(),
                }
              : item
        )
    );
  };

  /*
   * -------------------------------------------------------
   * ACCEPT
   * -------------------------------------------------------
   */

  const handleAcceptSuggestion =
    async (suggestion) => {
      try {
        if (
          typeof onAcceptSuggestion ===
          "function"
        ) {
          await onAcceptSuggestion(
            {
              ...suggestion,
              status: "accepted",
            }
          );
        }

        updateLocalSuggestion(
          suggestion,
          "accepted"
        );
        setReviewedDecision("approved");
      } catch {
        /*
         * Parent handles the error.
         * Do not mark it accepted if API failed.
         */
      }
    };

  /*
   * -------------------------------------------------------
   * REJECT
   * -------------------------------------------------------
   */

  const handleRejectSuggestion =
    async (suggestion) => {
      try {
        if (
          typeof onRejectSuggestion ===
          "function"
        ) {
          await onRejectSuggestion(
            {
              ...suggestion,
              status: "rejected",
            }
          );
        }

        updateLocalSuggestion(
          suggestion,
          "rejected"
        );
        setReviewedDecision("rejected");
      } catch {
        /*
         * Parent handles the error.
         */
      }
    };

  /*
   * -------------------------------------------------------
   * FINAL REVIEW DECISION
   * -------------------------------------------------------
   */

  const hasReviewedSuggestion =
    localSuggestions.some(
      (suggestion) => {
        const status =
          getSuggestionStatus(
            suggestion
          );

        return (
          status === "accepted" ||
          status === "modified" ||
          status === "rejected" ||
          status === "ignored"
        );
      }
    );

  const hasAcceptedSuggestion =
    localSuggestions.some(
      (suggestion) => {
        const status =
          getSuggestionStatus(
            suggestion
          );

        return (
          status === "accepted" ||
          status === "modified"
        );
      }
    );

  const reviewDecision =
    reviewedDecision ||
    (hasAcceptedSuggestion
      ? "approved"
      : hasReviewedSuggestion
      ? "rejected"
      : null);

  const handleFinalReview =
    async () => {
      if (
        !hasReviewedSuggestion ||
        !reviewDecision ||
        typeof onReviewComplete !==
          "function"
      ) {
        return;
      }

      try {
        await onReviewComplete(
          reviewDecision
        );
      } catch {
        /*
         * Parent handles the API error.
         * Drawer remains open if final status
         * update failed.
         */
      }
    };

  const getSuggestionText =
    (suggestion) =>
      suggestion?.suggestion_text ||
      suggestion?.message ||
      suggestion?.description ||
      suggestion?.suggestion ||
      "AI recommendation available.";

  /*
   * -------------------------------------------------------
   * RENDER
   * -------------------------------------------------------
   */

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
            <h2>
              Requirement Details
            </h2>

            <p>
              Review requirement
              validation findings
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

        {/* CONTENT */}

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
                String(
                  requirement?.status ||
                    "pending"
                )
                  .toLowerCase()
                  .replace(
                    /\s+/g,
                    "-"
                  )
              }`}
            >
              {String(
                requirement?.status ||
                  "pending"
              ).toLowerCase() ===
              "pending"
                ? "Pending Review"
                : String(
                    requirement?.status ||
                      "pending"
                  )
                    .charAt(0)
                    .toUpperCase() +
                  String(
                    requirement?.status ||
                      "pending"
                  ).slice(1)}
            </span>
          </section>

          {/* SOURCE DOCUMENT */}

          <section className="drawer-section">
            <div className="drawer-section-title">
              <FileText size={17} />

              <span>
                Source Document
              </span>
            </div>

            <div className="source-document-card">
              <div className="source-document-info">
                <div className="source-file-icon">
                  <FileText
                    size={18}
                  />
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
                  onClick={
                    openSourceDocument
                  }
                >
                  <span>
                    Open
                  </span>

                  <ExternalLink
                    size={15}
                  />
                </button>
              )}
            </div>
          </section>

          {/* REQUIREMENT */}

          <section className="drawer-section">
            <div className="drawer-section-title requirement-title">
              <FileText size={17} />

              <span>
                Requirement
              </span>
            </div>

            <div className="requirement-text-card">
              <p>
                {requirementText}
              </p>

              <button
                type="button"
                className="copy-requirement-button"
                onClick={
                  copyRequirement
                }
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
                <h3>
                  Rule Engine Findings
                </h3>

                <p>
                  {
                    findings.length
                  }{" "}
                  {findings.length ===
                  1
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
              {findings.length ===
                0 && (
                <div className="no-findings">
                  No validation
                  findings are
                  available.
                </div>
              )}

              {findings.map(
                (
                  finding,
                  index
                ) => {
                  const passed =
  finding?.passed === true;
                  const expanded =
                    expandedFinding ===
                    index;

                  const matchedRules =
                    getMatchedRules(
                      finding
                    );

                  const severity =
                    getFindingSeverity(
                      finding
                    );

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
                          toggleFinding(
                            index
                          )
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
                                size={
                                  18
                                }
                              />
                            ) : (
                              <AlertTriangle
                                size={
                                  18
                                }
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
                              {finding?.waived
                                ? "Waived"
                                : passed
                                ? "Passed"
                                : "Failed"}
                            </span>
                          </div>

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
                                          {getRuleDescription(
                                            rule
                                          )}
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
                                            {getRuleWhyItMatters(
                                              rule
                                            )}
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
                                            {getRuleRecommendation(
                                              rule
                                            )}
                                          </p>
                                        </div>
                                      )}
                                    </div>
                                  )
                                )}
                              </div>
                            </div>
                          )}

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

                          {typeof onWaiveFinding ===
                            "function" &&
                            (!passed || finding?.waived) && (
                              <div className="finding-detail">
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-small"
                                  disabled={waiveBusy}
                                  onClick={async () => {
                                    setWaiveBusy(true);

                                    try {
                                      await onWaiveFinding(
                                        finding,
                                        !finding?.waived
                                      );
                                    } catch {
                                      /* error is shown by the page */
                                    } finally {
                                      setWaiveBusy(false);
                                    }
                                  }}
                                >
                                  {finding?.waived
                                    ? "Remove waiver"
                                    : "Waive this issue (accept as-is)"}
                                </button>
                              </div>
                            )}
                        </div>
                      )}
                    </article>
                  );
                }
              )}
            </div>
          </section>

          {/* AI SUGGESTIONS */}

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
                {
                  localSuggestions.length
                }{" "}
                {localSuggestions.length ===
                1
                  ? "Suggestion"
                  : "Suggestions"}
              </span>
            </div>

            <div className="ai-suggestions-list">
              {reviewedDecision === "approved" ||
              localSuggestions.length === 0 ? (
                <div className="no-findings">
                  No AI suggestions
                  are available
                  for this
                  requirement.
                </div>
              ) : (
                localSuggestions.map(
                  (
                    suggestion,
                    index
                  ) => {
                    const suggestionStatus =
                      getSuggestionStatus(
                        suggestion
                      );

                    const accepted =
                      suggestionStatus ===
                        "accepted" ||
                      suggestionStatus ===
                        "modified";

                    const rejected =
                      suggestionStatus ===
                        "rejected" ||
                      suggestionStatus ===
                        "ignored";

                    return (
                      <div
                        className="ai-suggestion-card"
                        key={
                          suggestion?.id ||
                          `${getSuggestionText(
                            suggestion
                          )}-${index}`
                        }
                      >
                        <div className="ai-suggestion-icon">
                          <Sparkles
                            size={17}
                          />
                        </div>

                        <div className="ai-suggestion-content">
                          <p>
                            {getSuggestionText(
                              suggestion
                            )}
                          </p>

                          {suggestion?.suggestion_type && (
                            <span className="ai-suggestion-type">
                              {String(
                                suggestion.suggestion_type
                              )
                                .replaceAll(
                                  "_",
                                  " "
                                )
                                .replace(
                                  /\b\w/g,
                                  (
                                    char
                                  ) =>
                                    char.toUpperCase()
                                )}
                            </span>
                          )}

                          {accepted && (
                            <span className="ai-suggestion-status accepted">
                              <CheckCircle2
                                size={
                                  14
                                }
                              />

                              Accepted
                            </span>
                          )}

                          {rejected && (
                            <span className="ai-suggestion-status rejected">
                              <AlertTriangle
                                size={
                                  14
                                }
                              />

                              Rejected
                            </span>
                          )}

                          {!accepted &&
                            !rejected && (
                              <div className="ai-suggestion-actions">
                                <button
                                  type="button"
                                  className="suggestion-accept"
                                  onClick={() =>
                                    handleAcceptSuggestion(
                                      suggestion
                                    )
                                  }
                                >
                                  <ThumbsUp
                                    size={
                                      14
                                    }
                                  />

                                  Accept
                                </button>

                                <button
                                  type="button"
                                  className="suggestion-reject"
                                  onClick={() =>
                                    handleRejectSuggestion(
                                      suggestion
                                    )
                                  }
                                >
                                  <ThumbsDown
                                    size={
                                      14
                                    }
                                  />

                                  Reject
                                </button>
                              </div>
                            )}
                        </div>
                      </div>
                    );
                  }
                )
              )}
            </div>
          </section>

          {/* QUALITY SCORE */}

          <section className="drawer-section quality-score-section">
            <div className="findings-heading">
              <div>
                <h3>
                  Quality Score
                </h3>

                <p>
                  AI-assisted
                  requirement
                  quality
                  assessment
                </p>
              </div>
            </div>

            <div className="quality-score-card">
              {qualityScore !==
                null &&
              qualityScore !==
                undefined ? (
                <>
                  <div className="quality-score-main">
                    <div className="quality-score-value">
                      {
                        qualityScore
                      }

                      <span>
                        /100
                      </span>
                    </div>

                    <div className="quality-score-caption">
                      Requirement
                      quality
                      score
                    </div>
                  </div>

                  {qualityAssessment && (
                    <div className="quality-dimensions">
                      {qualityDimensions.map(
                        (
                          dimension
                        ) => {
                          const value =
                            qualityAssessment?.[
                              dimension.key
                            ];

                          const dimensionClass =
                            getQualityDimensionClass(
                              value
                            );

                          const progress =
                            getQualityDimensionProgress(
                              value
                            );

                          return (
                            <div
                              className="quality-dimension"
                              key={
                                dimension.key
                              }
                            >
                              <div className="quality-dimension-header">
                                <span>
                                  {
                                    dimension.label
                                  }
                                </span>

                                <span
                                  className={`quality-dimension-status ${dimensionClass}`}
                                  title={String(
                                    value ||
                                      ""
                                  )}
                                >
                                  {String(
                                    value ||
                                      getQualityDimensionStatus(
                                        value
                                      )
                                  )}
                                </span>
                              </div>

                              <div className="quality-progress-track">
                                <div
                                  className={`quality-progress-bar ${dimensionClass}`}
                                  style={{
                                    width: `${progress}%`,
                                  }}
                                />
                              </div>
                            </div>
                          );
                        }
                      )}
                    </div>
                  )}
                </>
              ) : (
                <div className="quality-score-empty">
                  Quality score is
                  not available
                  yet.
                </div>
              )}
            </div>
          </section>
        </div>

        {/* FINAL OK */}

        <div className="review-final-action">
          <button
            type="button"
            className="review-final-ok"
            disabled={
              !hasReviewedSuggestion
            }
            onClick={
              handleFinalReview
            }
          >
            OK
          </button>
        </div>
      </aside>
    </div>
  );
}

export default RuleDetailsModal;