import {
  Eye,
  AlertTriangle,
  CheckCircle2,
  Search,
} from "lucide-react";

import StatusPill from "../../requirements/components/StatusPill";

function RuleTable({
  requirements,
  search,
  onSearchChange,
  onSelectRule,
  
}) {
  const searchTerm =
    search?.trim().toLowerCase() || "";

  const filteredRequirements =
    requirements.filter((req) => {
      if (!searchTerm) {
        return true;
      }

      const requirementId =
        req.requirement_code ||
        req.code ||
        "";

      const requirementText =
        req.draft_requirement_text ||
        req.current_requirement_text ||
        req.requirement_text ||
        req.text ||
        req.title ||
        "";

      return (
        String(requirementId)
          .toLowerCase()
          .includes(searchTerm) ||
        String(requirementText)
          .toLowerCase()
          .includes(searchTerm)
      );
    });

  return (
    <div className="rule-results-card">
      <div className="rule-results-header">
        <div className="rule-search-wrapper">
          <Search
            size={19}
            className="rule-search-icon"
          />

          <input
            type="text"
            className="rule-search-input"
            placeholder="Search requirements by ID or keywords..."
            value={search || ""}
            onChange={(event) =>
              onSearchChange(event.target.value)
            }
          />
        </div>
      </div>

      <div className="rule-table-wrapper">
        <table className="rule-table">
          <colgroup>
            <col className="rule-col-id" />
            <col className="rule-col-requirement" />
            <col className="rule-col-source" />
            <col className="rule-col-quality" />
            <col className="rule-col-status" />
            <col className="rule-col-issues" />
            <col className="rule-col-action" />
          </colgroup>

          <thead>
            <tr>
              <th>Requirement ID</th>
              <th>Requirement</th>
              <th>Source Document</th>
              <th>Quality Score</th>
              <th>Status</th>
              <th>Issues</th>
              <th>Action</th>
            </tr>
          </thead>

          <tbody>
            {filteredRequirements.length > 0 ? (
              filteredRequirements.map((req) => {
                const findings = Array.isArray(
                  req.findings
                )
                  ? req.findings
                  : [];

                const failedFindings =
                  findings.filter(
                    (finding) =>
                      finding?.passed === false
                  );

                const issueCount =
                  failedFindings.length;

                const qualityScore =
                  req.quality_score;

                const hasDraft = Boolean(
                  String(
                    req.draft_requirement_text || ""
                  ).trim()
                );

                const requirementText =
                  req.draft_requirement_text ||
                  req.current_requirement_text ||
                  req.requirement_text ||
                  req.text ||
                  req.title ||
                  "Untitled Requirement";

                const requirementId =
                  req.requirement_code ||
                  req.code ||
                  "—";

                const sourceDocument =
                  req.source_document_name ||
                  req.source_document
                    ?.original_filename ||
                  req.source_document
                    ?.filename ||
                  req.original_filename ||
                  req.source_name ||
                  "—";

                return (
                  <tr key={req.id}>
                    <td>
                      <strong className="requirement-id">
                        {requirementId}
                      </strong>
                    </td>

                    <td>
                      <div className="requirement-cell">
                        <span>
                          {requirementText}
                        </span>
                      </div>
                    </td>

                    <td>
                      <div className="rule-source-document">
                        {sourceDocument}
                      </div>
                    </td>

                    <td>
                      <div className="rule-quality-score">
                        {qualityScore !== null &&
                        qualityScore !== undefined &&
                        Number.isFinite(
                          Number(qualityScore)
                        )
                          ? `${Math.round(
                              Number(
                                qualityScore
                              )
                            )}/100`
                          : "—"}
                      </div>

                      {issueCount > 0 && (
                        <small className="rule-score-note">
                          {issueCount} rule issue
                          {issueCount === 1 ? "" : "s"} open
                        </small>
                      )}
                    </td>

                    <td>
                      <StatusPill
                        status={
                          req.status ||
                          "pending"
                        }
                      />

                      {hasDraft && (
                        <small className="rule-draft-note">
                          Draft awaiting analysis
                        </small>
                      )}
                    </td>

                    <td>
                      <div
                        className={`rule-issue-count ${
                          issueCount > 0
                            ? "has-issues"
                            : "no-issues"
                        }`}
                      >
                        {issueCount > 0 ? (
                          <AlertTriangle
                            size={15}
                          />
                        ) : (
                          <CheckCircle2
                            size={15}
                          />
                        )}

                        <span>
                          {issueCount}
                        </span>
                      </div>
                    </td>

                    <td>
             
                      <button
                        type="button"
                        className="view-rule-button"
                        onClick={() =>
                          onSelectRule(req)
                        }
                      >
                        <Eye size={15} />
                        <span>View</span>
                      </button>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td
                  colSpan="8"
                  className="rule-no-results"
                >
                  No requirements found matching
                  your search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default RuleTable;