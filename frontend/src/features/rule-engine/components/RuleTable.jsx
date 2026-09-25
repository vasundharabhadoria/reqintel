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

  /*
   * Search only:
   * 1. Requirement ID
   * 2. Requirement text / keywords
   *
   * Title is intentionally NOT included.
   */
  const filteredRequirements =
    requirements.filter((req) => {
      if (!searchTerm) return true;

      const requirementId =
        req.requirement_code || "";

      const requirementText =
        req.current_requirement_text || "";

      return (
        requirementId
          .toLowerCase()
          .includes(searchTerm) ||
        requirementText
          .toLowerCase()
          .includes(searchTerm)
      );
    });

  return (
    <div className="rule-results-card">

      {/* SEARCH */}

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

      {/* TABLE */}

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
                const findings =
                  req.findings || [];

                const failedFindings =
                  findings.filter(
                    (finding) =>
                      finding.passed === false
                  );

                const issueCount =
                  failedFindings.length;

                return (
                  <tr key={req.id}>

                    {/* REQUIREMENT ID */}

                    <td>
                      <strong className="requirement-id">
                        {req.requirement_code ||
                          "RQ-001"}
                      </strong>
                    </td>

                    {/* REQUIREMENT */}

                    <td>
                      <div className="requirement-cell">
                        <span>
                          {req.current_requirement_text ||
                            req.title ||
                            "Untitled Requirement"}
                        </span>
                      </div>
                    </td>

                    {/* SOURCE DOCUMENT */}

                    <td>
                      <div className="rule-source-document">
                        {req.source_document_name ||
                          req.source_document
                            ?.original_filename ||
                          req.original_filename ||
                          req.source
                            ?.original_filename ||
                          req.source_name ||
                          "—"}
                      </div>
                    </td>

                    {/* QUALITY SCORE */}

                    <td>
                      <div className="rule-quality-score">
                        {req.quality_score ??
                          req.qualityScore ??
                          "—"}
                      </div>
                    </td>

                    {/* STATUS */}

                    <td>
                      <StatusPill
                        status={
                          req.status || "pending"
                        }
                      />
                    </td>

                    {/* ISSUES */}

                    <td>
                      <div
                        className={`rule-issue-count ${
                          issueCount > 0
                            ? "has-issues"
                            : "no-issues"
                        }`}
                      >
                        {issueCount > 0 ? (
                          <AlertTriangle size={15} />
                        ) : (
                          <CheckCircle2 size={15} />
                        )}

                        <span>
                          {issueCount}
                        </span>
                      </div>
                    </td>

                    {/* ACTION */}

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
                  colSpan="7"
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