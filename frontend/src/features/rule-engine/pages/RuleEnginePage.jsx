import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { ShieldCheck, RefreshCw, Sparkles } from "lucide-react";

import {
  listRequirements,
  listSources,
  getSavedProjectAnalysis,
  analyzeRequirements,
  acceptSuggestion,
  rejectSuggestion,
  approveRequirement,
  rejectRequirement,
  waiveIssue,
  removeIssueWaiver,
} from "../../../api/requirementsApi";
import { useToast } from "../../../hooks/useToast";

import { getProject } from "../../../api/projectApi";

import AppShell from "../../../components/layout/AppShell";

import RuleEngineHeader from "../components/RuleEngineHeader";
import RuleStatsCards from "../components/RuleStatsCards";
import RuleTable from "../components/RuleTable";
import RuleDetailsModal from "../components/RuleDetailsModal";
import { useCurrentRepositoryVersion } from "../../versions/hooks/useCurrentRepositoryVersion";
import "../styles/rule-engine.css";


function parseRawAIResponse(rawResponse) {
  if (!rawResponse) {
    return null;
  }

  if (typeof rawResponse === "object") {
    return rawResponse;
  }

  if (typeof rawResponse === "string") {
    try {
      return JSON.parse(rawResponse);
    } catch {
      return null;
    }
  }

  return null;
}


function normalizeQualityValue(value) {
  if (value === null || value === undefined) {
    return "";
  }

  const rawValue = String(value)
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/\*\*/g, "")
    .replace(/__/g, "")
    .replace(/^[-•*]\s*/, "")
    .replace(/\s+/g, " ")
    .trim();

  if (!rawValue) {
    return "";
  }

  const match = rawValue.match(
    /\b(excellent|high|good|clear|complete|consistent|medium|moderate|fair|low|poor|incomplete|inconsistent|ambiguous|needs improvement)\b/i
  );

  if (!match) {
    return "";
  }

  const level = match[1].toLowerCase();

  if (
    level === "excellent" ||
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
    level === "moderate" ||
    level === "fair"
  ) {
    return "medium";
  }

  return "low";
}


function getQualityDimensionScore(dimension, value) {
  const level = normalizeQualityValue(value);

  const scores = {
    clarity: { high: 17, medium: 12, low: 6 },
    completeness: { high: 17, medium: 12, low: 6 },
    unambiguity: { high: 15, medium: 10, low: 5 },
    consistency: { high: 17, medium: 12, low: 6 },
    specificity: { high: 17, medium: 12, low: 6 },
    testability: { high: 17, medium: 12, low: 6 },
  };

  return scores[dimension]?.[level] ?? 0;
}


function calculateAIQualityScore(assessment) {
  if (!assessment || typeof assessment !== "object") {
    return null;
  }

  const dimensions = [
    "clarity",
    "completeness",
    "unambiguity",
    "consistency",
    "specificity",
    "testability",
  ];

  let assessedDimensions = 0;

  const total = dimensions.reduce(
    (sum, dimension) => {
      const value = assessment?.[dimension];
      const level = normalizeQualityValue(value);

      if (!level) {
        return sum;
      }

      assessedDimensions += 1;

      return (
        sum +
        getQualityDimensionScore(
          dimension,
          value
        )
      );
    },
    0
  );

  if (assessedDimensions === 0) {
    return null;
  }

  return Math.max(
    0,
    Math.min(100, Math.round(total))
  );
}


function getIssueDeduction(finding) {
  const severity = String(
    finding?.severity || "Medium"
  )
    .trim()
    .toLowerCase();

  if (severity === "critical") return 20;
  if (severity === "high") return 12;
  if (severity === "medium") return 7;
  if (severity === "low") return 3;

  return 5;
}


function calculateFinalQualityScore(
  assessment,
  _findings
) {
  /*
   * AI Quality Score is based ONLY on the six AI quality dimensions:
   *
   * - clarity
   * - completeness
   * - unambiguity
   * - consistency
   * - specificity
   * - testability
   *
   * Rule Engine issues are displayed separately and must not be
   * subtracted from the AI quality score.
   *
   * This keeps the two measurements independent:
   *   Rule Engine -> engineering/rule compliance
   *   AI Quality  -> six quality dimensions
   */
  return calculateAIQualityScore(assessment);
}


function RuleEnginePage() {
  const { projectId } = useParams();
  const { showToast } = useToast();

  const [project, setProject] =
    useState(null);

  const [projectLoading, setProjectLoading] =
    useState(true);

  const [requirements, setRequirements] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [selectedRule, setSelectedRule] =
    useState(null);
const [selectedImpactRule, setSelectedImpactRule] = useState(null);
  const [search, setSearch] =
    useState("");

  const [analyzeEnabled, setAnalyzeEnabled] =
    useState(false);

  const [analyzing, setAnalyzing] =
    useState(false);


  const fetchProject =
    useCallback(async () => {
      if (!projectId) {
        return;
      }

      setProjectLoading(true);

      try {
        const data =
          await getProject(projectId);

        setProject(data);
      } catch (err) {
        console.error(
          "Failed to load project:",
          err
        );
      } finally {
        setProjectLoading(false);
      }
    }, [projectId]);


  const fetchRequirements =
    useCallback(async () => {
      if (!projectId) {
        return;
      }

      setLoading(true);
      setError("");

      try {
        const [
          requirementsData,
          sourceData,
          analysisData,
        ] = await Promise.all([
          listRequirements(projectId),
          listSources(projectId),
          getSavedProjectAnalysis(
            projectId
          ),
        ]);

        const items =
          requirementsData?.items || [];

        const sources =
          sourceData?.items || [];

        const results =
          analysisData?.results || [];

        const hasRequirements =
          items.length > 0;

        const requiresAIAnalysis =
          Boolean(
            analysisData?.requires_ai_analysis
          );

        const hasUnanalyzedChanges =
          Boolean(
            analysisData?.has_unanalyzed_changes
          );

        const hasReviewedRequirements =
          items.some((item) => {
            const status = String(
              item?.status || ""
            ).toLowerCase();

            return (
              status === "approved" ||
              status === "rejected"
            );
          });

        /*
         * V1 is analyzed by the Requirements-page Analyze action.
         * After BA Accept/Reject + OK, this page must enable Analyze
         * again. The next Analyze click is what creates the next
         * repository version.
         */
        setAnalyzeEnabled(
          hasRequirements &&
          (requiresAIAnalysis ||
            hasUnanalyzedChanges ||
            hasReviewedRequirements)
        );


        const sourcesById =
          new Map(
            sources.map((source) => [
              String(source.id),
              source,
            ])
          );


        const findingsByRequirementId =
          new Map(
            results.map((result) => [
              String(result.id),
              result.findings || [],
            ])
          );


        const aiResults =
          Array.isArray(
            analysisData?.ai_results
          )
            ? analysisData.ai_results
            : [];


        const aiByRequirementId =
          new Map(
            aiResults.map((item) => [
              String(item.requirement_id),
              item,
            ])
          );


        const mergedRequirements =
          items.map((requirement) => {
            const source =
              requirement.source_id
                ? sourcesById.get(
                    String(
                      requirement.source_id
                    )
                  )
                : null;


            const sourceUrl =
              requirement.source_document_url ||
              requirement.file_url ||
              requirement.download_url ||
              source?.url ||
              source?.file_url ||
              source?.download_url ||
              source?.document_url ||
              source?.file_path ||
              source?.path ||
              null;


            const aiResult =
              aiByRequirementId.get(
                String(requirement.id)
              );


            const hasDraft =
              Boolean(
                String(
                  requirement?.draft_requirement_text ||
                    ""
                ).trim()
              );


            /*
             * Rule Engine is the source of truth for whether an
             * AI suggestion is required.
             *
             * - ALL findings passed -> no suggestion
             * - ANY finding not passed -> exactly one suggestion
             */
            const failedFindings = findingsByRequirementId
              .get(String(requirement.id))
              ?.filter(
                (finding) =>
                  finding?.passed !== true
              ) || [];

            const savedAiSuggestions =
              Array.isArray(
                aiResult?.suggestions
              )
                ? aiResult.suggestions
                : [];

            const aiSuggestions =
              failedFindings.length > 0
                ? savedAiSuggestions.slice(0, 1)
                : [];


            /*
             * IMPORTANT:
             *
             * Accepting a suggestion immediately creates the next
             * repository version on the backend. The response is
             * followed by a full database reload so the new version
             * becomes the source of truth for the UI.
             */
            const aiAnalysis = hasDraft
              ? null
              : aiResult?.analysis ||
                null;


            const rawAiResponse =
              parseRawAIResponse(
                aiAnalysis?.raw_response_json
              );


            /*
             * IMPORTANT:
             *
             * Never clear findings just because a draft exists.
             *
             * The existing findings belong to the current
             * repository version and must remain visible until
             * Analyze Requirements creates the next version.
             */
            const findings =
              findingsByRequirementId.get(
                String(requirement.id)
              ) || [];


            const qualityAssessment =
              rawAiResponse
                ?.quality_assessment ||
              null;


            /*
             * Quality score must be unavailable while an
             * accepted suggestion is waiting to be analyzed.
             */
            const finalQualityScore =
              hasDraft
                ? null
                : calculateFinalQualityScore(
                    qualityAssessment,
                    findings
                  );


            const storedQualityScore =
              hasDraft
                ? null
                : Number.isFinite(
                    Number(
                      requirement?.quality_score
                    )
                  ) &&
                  Number(
                    requirement.quality_score
                  ) > 0
                ? Number(
                    requirement.quality_score
                  )
                : Number.isFinite(
                    Number(
                      requirement?.final_quality_score
                    )
                  ) &&
                  Number(
                    requirement.final_quality_score
                  ) > 0
                ? Number(
                    requirement.final_quality_score
                  )
                : null;


            const displayRequirementText =
              hasDraft
                ? String(
                    requirement?.draft_requirement_text ||
                      requirement?.current_requirement_text ||
                      requirement?.requirement_text ||
                      requirement?.text ||
                      ""
                  )
                : String(
                    requirement?.current_requirement_text ||
                      requirement?.requirement_text ||
                      requirement?.text ||
                      ""
                  );

            return {
              ...requirement,

              /*
               * The accepted draft is shown immediately in the UI.
               * It is still only a draft in the database until Analyze
               * creates the next repository version.
               */
              current_requirement_text:
                displayRequirementText,
              requirement_text:
                displayRequirementText,
              text: displayRequirementText,

              findings,

              ai_suggestions:
                aiSuggestions,

              ai_analysis:
                aiAnalysis,

              ai_quality_assessment:
                qualityAssessment,

              quality_score:
                finalQualityScore !== null
                  ? finalQualityScore
                  : storedQualityScore,

              ai_ambiguity_detected:
                Boolean(
                  aiAnalysis
                    ?.ambiguity_detected ??
                    rawAiResponse
                      ?.ambiguity_detected
                ),

              source_document_name:
                requirement
                  .source_document_name ||
                source?.original_filename ||
                source?.filename ||
                "—",

              source_document_url:
                sourceUrl,

              source_document:
                source,
            };
          });


        setRequirements(
          mergedRequirements
        );

      } catch (err) {
        console.error(
          "Failed to load rule engine:",
          err
        );

        setError(
          err?.message ||
            "Failed to load rule engine data."
        );
      } finally {
        setLoading(false);
      }
    }, [projectId]);


  const handleAnalyze =
    useCallback(async () => {
      if (
        !projectId ||
        analyzing
      ) {
        return;
      }

      setAnalyzing(true);
      setError("");

      try {
        const analyzeResponse =
          await analyzeRequirements(
            projectId
          );

        /*
         * Analyze is always available. When nothing changed since the
         * current version, the backend re-uses the saved analysis (no AI
         * call, no new version) and we simply say so.
         */
        if (analyzeResponse?.repository_version_skipped_reason) {
          showToast(
            analyzeResponse.repository_version_skipped_reason,
            "error"
          );
        } else if (
          analyzeResponse?.repository_version_created
        ) {
          showToast(
            `Repository Version ${analyzeResponse.repository_version} created.`,
            "success"
          );
        } else if (analyzeResponse?.cached) {
          showToast(
            `No changes since Version ${
              analyzeResponse.repository_version ?? ""
            }. Accept a suggestion or waive an issue to create a new version.`,
            "success"
          );
        }

        setAnalyzeEnabled(false);
        setSelectedRule(null);

        await fetchRequirements();

      } catch (err) {
        console.error(
          "Failed to analyze requirements:",
          err
        );

        setError(
          err?.message ||
            "Failed to analyze requirements."
        );
      } finally {
        setAnalyzing(false);
      }
    }, [
      projectId,
      analyzing,
      fetchRequirements,
      showToast,
    ]);


  /*
   * ACCEPT AI SUGGESTION
   *
   * Accepting a suggestion:
   *
   * 1. Saves the suggestion as accepted.
   * 2. Immediately creates the next repository version.
   * 3. Reloads the database-backed V2 state.
   * 4. Enables Analyze Requirements for the new V2.
   * 5. Does not mutate V1 or fabricate frontend findings.
   */

  const handleAcceptSuggestion =
    useCallback(
      async (suggestion) => {
        if (
          !projectId ||
          !selectedRule?.id ||
          !suggestion?.id
        ) {
          return;
        }

        try {
          const response =
            await acceptSuggestion(
              projectId,
              selectedRule.id,
              suggestion.id
            );
console.log("Accept suggestion response:", response);
console.log("Updated requirement:", response?.requirement);

          const updatedRequirement =
            response?.requirement || {};

          const updatedSuggestion =
            response?.suggestion || {};

          const draftText =
            String(
              updatedRequirement?.draft_requirement_text ||
                updatedSuggestion?.resolved_text ||
                suggestion?.resolved_text ||
                ""
            ).trim();

          const updateItem = (item) => {
            if (
              String(item.id) !==
              String(selectedRule.id)
            ) {
              return item;
            }

            return {
              ...item,
              ...updatedRequirement,
              ...(draftText
                ? {
                    draft_requirement_text: draftText,
                    current_requirement_text: draftText,
                    requirement_text: draftText,
                    text: draftText,
                  }
                : {}),
              status: item.status || "pending",

              /* Keep V1 findings exactly as they are. */
              findings: Array.isArray(item.findings)
                ? item.findings
                : [],

              /* Accepted review removes the old AI result from the UI. */
              ai_suggestions: [],
              ai_analysis: null,
              ai_quality_assessment: null,
              quality_score: null,
              final_quality_score: null,
            };
          };

          setRequirements((current) =>
            current.map(updateItem)
          );

          setSelectedRule((current) =>
            current ? updateItem(current) : current
          );

          /* Analyze is available immediately; version remains V1. */
          setAnalyzeEnabled(true);
        } catch (err) {
          console.error(
            "Failed to accept AI suggestion:",
            err
          );

          setError(
            err?.message ||
              "Failed to accept AI suggestion."
          );

          throw err;
        }
      },
      [
        projectId,
        selectedRule,
      ]
    );

  const handleRejectSuggestion =
    useCallback(
      async (suggestion) => {
        if (
          !projectId ||
          !selectedRule?.id ||
          !suggestion?.id
        ) {
          return;
        }

        try {
          const response =
            await rejectSuggestion(
              projectId,
              selectedRule.id,
              suggestion.id
            );

          const updatedSuggestion =
            response?.suggestion || {};

          const updateItem = (item) => {
            if (
              String(item.id) !==
              String(selectedRule.id)
            ) {
              return item;
            }

            return {
              ...item,

              /* Keep existing Rule Engine findings and score. */
              findings: Array.isArray(item.findings)
                ? item.findings
                : [],

              ai_suggestions: (
                item.ai_suggestions || []
              ).map((saved) =>
                String(saved.id) ===
                String(suggestion.id)
                  ? {
                      ...saved,
                      ...updatedSuggestion,
                      status: "ignored",
                    }
                  : saved
              ),
            };
          };

          setRequirements((current) =>
            current.map(updateItem)
          );

          setSelectedRule((current) =>
            current ? updateItem(current) : current
          );

          /* Reject does not create a version; Analyze remains active. */
          setAnalyzeEnabled(true);
        } catch (err) {
          console.error(
            "Failed to reject AI suggestion:",
            err
          );

          setError(
            err?.message ||
              "Failed to reject AI suggestion."
          );

          throw err;
        }
      },
      [projectId, selectedRule]
    );


  /*
   * WAIVE / UN-WAIVE an issue (Business Analyst accepts it as-is).
   * The backend re-evaluates the requirement status; the next Analyze
   * click records the change in the repository version history.
   */
  const handleWaiveFinding =
    useCallback(
      async (finding, waive, reason = "") => {
        if (!projectId || !selectedRule?.id) {
          return;
        }

        const ruleName = String(
          finding?.rule_name ||
            finding?.category ||
            ""
        );

        try {
          const response = waive
            ? await waiveIssue(
                projectId,
                selectedRule.id,
                ruleName,
                reason
              )
            : await removeIssueWaiver(
                projectId,
                selectedRule.id,
                ruleName
              );

          const updateItem = (item) => {
            if (
              String(item.id) !==
              String(selectedRule.id)
            ) {
              return item;
            }

            return {
              ...item,
              status:
                response?.status || item.status,
              findings: (item.findings || []).map(
                (current) =>
                  String(
                    current?.rule_name ||
                      current?.category ||
                      ""
                  ) === ruleName
                    ? {
                        ...current,
                        passed: Boolean(waive),
                        waived: Boolean(waive),
                        waived_reason: waive
                          ? reason
                          : undefined,
                      }
                    : current
              ),
            };
          };

          setRequirements((current) =>
            current.map(updateItem)
          );

          setSelectedRule((current) =>
            current ? updateItem(current) : current
          );
        } catch (err) {
          console.error(
            "Failed to update issue waiver:",
            err
          );

          setError(
            err?.message ||
              "Failed to update the issue waiver."
          );

          throw err;
        }
      },
      [projectId, selectedRule]
    );


  /*
   * FINAL OK ACTION
   *
   * The drawer decides whether the final status is:
   *
   * accepted suggestion exists -> approved
   * otherwise reviewed/rejected suggestion exists -> rejected
   *
   * X never calls this function.
   *
   * Important:
   * This operation only changes the review status.
   * Version creation happens on the next Analyze click.
   */

  const handleReviewComplete =
    useCallback(
      async (decision) => {
        if (
          !projectId ||
          !selectedRule?.id
        ) {
          return;
        }

        const isApproved =
          decision === "approved";

        try {
          if (isApproved) {
            await approveRequirement(
              projectId,
              selectedRule.id
            );
          } else {
            await rejectRequirement(
              projectId,
              selectedRule.id
            );
          }

          setSelectedRule(null);
          setAnalyzeEnabled(true);
          await fetchRequirements();
        } catch (err) {
          console.error(
            "Failed to update requirement review status:",
            err
          );

          setError(
            err?.message ||
              "Failed to update the requirement status."
          );

          throw err;
        }
      },
      [
        projectId,
        selectedRule,
        fetchRequirements,
      ]
    );

  useEffect(() => {
    fetchProject();
    fetchRequirements();
  }, [fetchProject, fetchRequirements]);

  const stats = useMemo(() => {
    const total =
      requirements.length;


    const pending =
      requirements.filter((req) => {
        const status =
          req.status?.toLowerCase();

        return (
          status === "pending" ||
          status === "pending review"
        );
      }).length;


    const approved =
      requirements.filter(
        (req) =>
          req.status?.toLowerCase() ===
          "approved"
      ).length;


    const rejected =
      requirements.filter(
        (req) =>
          req.status?.toLowerCase() ===
          "rejected"
      ).length;


    const drafts =
      requirements.filter((req) =>
        String(
          req.draft_requirement_text || ""
        ).trim()
      ).length;


    const issues =
      requirements.reduce(
        (count, requirement) =>
          count +
          (
            requirement.findings ||
            []
          ).filter(
            (finding) =>
              finding.passed === false
          ).length,
        0
      );


    const aiSuggestions =
      requirements.reduce(
        (count, requirement) => {
          const failedFindings =
            (
              requirement.findings ||
              []
            ).filter(
              (finding) =>
                finding?.passed !== true
            );

          if (failedFindings.length === 0) {
            return count;
          }

          const savedSuggestions =
            Array.isArray(
              requirement.ai_suggestions
            )
              ? requirement.ai_suggestions
              : [];

          return (
            count +
            Math.min(savedSuggestions.length, 1)
          );
        },
        0
      );


    return {
      total,
      pending,
      approved,
      rejected,
      aiSuggestions,
      issues,
      drafts,
    };
  }, [requirements]);


  const computedRepositoryVersion =
    useMemo(() => {
      const versions =
        requirements
          .map((requirement) =>
            Number(
              requirement
                .current_version_number
            )
          )
          .filter(
            (version) =>
              Number.isFinite(version) &&
              version > 0
          );


      return versions.length > 0
        ? Math.max(...versions)
        : null;
    }, [requirements]);

  // Source of truth is the repository_versions table; the value
  // computed above is only a fallback.
  const repositoryVersion =
    useCurrentRepositoryVersion(
      projectId,
      computedRepositoryVersion,
      requirements
    );


  return (
    <AppShell active="projects">
      <div className="rule-engine-page">

        <RuleEngineHeader
          project={project}
          projectLoading={
            projectLoading
          }
          repositoryVersion={
            repositoryVersion
          }
        />


        <section className="rule-engine-heading">
          <div className="rule-engine-heading-left">

            <div className="rule-engine-heading-icon">
              <ShieldCheck size={27} />
            </div>


            <div>
              <h2>
                Requirements
              </h2>

              <p>
                AI extracted requirements
                from your uploaded
                documents. Review,
                validate and manage them.
              </p>
            </div>
          </div>


          <button
            type="button"
            className="rule-analyze-button"
            disabled={
              analyzing ||
              loading ||
              requirements.length === 0
            }
            onClick={handleAnalyze}
          >
            {analyzing ? (
              <>
                <RefreshCw
                  size={16}
                  className="spin"
                />

                Analyzing...
              </>
            ) : (
              <>
                <Sparkles size={16} />

                Analyze Requirements
              </>
            )}
          </button>
        </section>


        <main className="rule-engine-content">

          <RuleStatsCards stats={stats} />


          {loading && (
            <div className="rule-state">

              <RefreshCw
                size={25}
                className="spin"
              />

              <p>
                Loading saved analysis...
              </p>
            </div>
          )}


          {!loading && error && (
            <div className="rule-state rule-error">

              <p>{error}</p>

              <button
                type="button"
                className="rule-retry-button"
                onClick={
                  fetchRequirements
                }
              >
                Try Again
              </button>
            </div>
          )}


          {!loading &&
            !error &&
            requirements.length === 0 && (
              <div className="rule-state">

                <p>
                  No extracted
                  requirements found
                  for this project.
                </p>

              </div>
            )}


          {!loading &&
            !error &&
            requirements.length > 0 && (
              <RuleTable
                requirements={
                  requirements
                }
                search={search}
                onSearchChange={
                  setSearch
                }
                onSelectRule={
                  setSelectedRule
                }
                onSelectImpact={setSelectedImpactRule}
              />
            )}

        </main>


        {selectedRule && (
          <RuleDetailsModal
            requirement={
              selectedRule
            }

            onClose={() =>
              setSelectedRule(null)
            }

            onAcceptSuggestion={
              handleAcceptSuggestion
            }

            onWaiveFinding={
              handleWaiveFinding
            }

            onRejectSuggestion={
              handleRejectSuggestion
            }

            onReviewComplete={
              handleReviewComplete
            }
          />
        )}
{selectedImpactRule && (
  <ImpactModal
    requirement={selectedImpactRule}
    onClose={() => setSelectedImpactRule(null)}
  />
)}
      </div>
    </AppShell>
  );
}


export default RuleEnginePage;