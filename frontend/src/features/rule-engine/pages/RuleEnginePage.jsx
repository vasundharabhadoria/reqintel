import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { ShieldCheck, RefreshCw } from "lucide-react";

import {
  listRequirements,
  analyzeRequirements,
  listSources,
} from "../../../api/requirementsApi";

import { getProject } from "../../../api/projectApi";

import AppShell from "../../../components/layout/AppShell";

import RuleEngineHeader from "../components/RuleEngineHeader";
import RuleStatsCards from "../components/RuleStatsCards";
import RuleTable from "../components/RuleTable";
import RuleDetailsModal from "../components/RuleDetailsModal";

import "../styles/rule-engine.css";

function RuleEnginePage() {
  const { projectId } = useParams();

  const [project, setProject] = useState(null);
  const [projectLoading, setProjectLoading] = useState(true);

  const [requirements, setRequirements] = useState([]);
  const [loading, setLoading] = useState(true);

  const [error, setError] = useState("");
  const [selectedRule, setSelectedRule] = useState(null);

  const [search, setSearch] = useState("");

  /*
   * ---------------------------------------------------------
   * LOAD PROJECT
   * ---------------------------------------------------------
   */

  const fetchProject = useCallback(async () => {
    if (!projectId) return;

    setProjectLoading(true);

    try {
      const data = await getProject(projectId);
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

  /*
   * ---------------------------------------------------------
   * LOAD REQUIREMENTS + SOURCES + ANALYSIS
   * ---------------------------------------------------------
   */

  const fetchRequirements = useCallback(async () => {
    if (!projectId) return;

    setLoading(true);
    setError("");

    const storageKey =
      `rule-engine-analysis-${projectId}`;

    try {
      /*
       * First check whether RequirementsPanel has
       * already completed the Rule Engine.
       */
      const cachedAnalysis =
        sessionStorage.getItem(storageKey);

      /*
       * Requirements and sources can be fetched
       * at the same time.
       */
      const [
        requirementsData,
        sourceData,
      ] = await Promise.all([
        listRequirements(projectId),
        listSources(projectId),
      ]);

      let analysisData = null;

      /*
       * Use cached analysis if available.
       */
      if (cachedAnalysis) {
        try {
          analysisData = JSON.parse(
            cachedAnalysis
          );
        } catch (parseError) {
          console.error(
            "Failed to parse cached analysis:",
            parseError
          );

          /*
           * Remove corrupted cache so that
           * the fallback can run correctly.
           */
          sessionStorage.removeItem(storageKey);
        }
      }

      /*
       * FALLBACK
       *
       * If the user directly opens Rule Engine
       * without going through Analyze Requirements,
       * run the analysis normally.
       */
      if (!analysisData) {
        analysisData =
          await analyzeRequirements(projectId);
      }

      const items =
        requirementsData?.items || [];

      const sources =
        sourceData?.items || [];

      const results =
        analysisData?.results || [];

      /*
       * -----------------------------------------------------
       * SOURCE LOOKUP
       * -----------------------------------------------------
       */

      const sourcesById = new Map(
        sources.map((source) => [
          String(source.id),
          source,
        ])
      );

      /*
       * -----------------------------------------------------
       * FINDINGS LOOKUP
       * -----------------------------------------------------
       */

      const findingsByRequirementId = new Map(
        results.map((result) => [
          String(result.id),
          result.findings || [],
        ])
      );

      /*
       * -----------------------------------------------------
       * MERGE REQUIREMENTS
       * -----------------------------------------------------
       */

      const mergedRequirements =
        items.map((requirement) => {
          const source = requirement.source_id
            ? sourcesById.get(
                String(requirement.source_id)
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

          return {
            ...requirement,

            findings:
              findingsByRequirementId.get(
                String(requirement.id)
              ) || [],

            source_document_name:
              requirement.source_document_name ||
              source?.original_filename ||
              source?.filename ||
              "—",

            source_document_url:
              sourceUrl,

            source_document: source,
          };
        });

      setRequirements(
        mergedRequirements
      );

      /*
       * Analysis has now been consumed.
       * Remove temporary cache.
       */
      sessionStorage.removeItem(
        storageKey
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

  /*
   * ---------------------------------------------------------
   * INITIAL LOAD
   * ---------------------------------------------------------
   */

  useEffect(() => {
    fetchProject();
    fetchRequirements();
  }, [
    fetchProject,
    fetchRequirements,
  ]);

  /*
   * ---------------------------------------------------------
   * STATISTICS
   * ---------------------------------------------------------
   */

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

    const issues =
      requirements.reduce(
        (count, requirement) => {
          return (
            count +
            (requirement.findings || [])
              .filter(
                (finding) =>
                  finding.passed === false
              ).length
          );
        },
        0
      );

    const aiSuggestions =
      requirements.reduce(
        (count, requirement) => {
          return (
            count +
            (requirement.findings || [])
              .filter(
                (finding) =>
                  finding.type ===
                    "suggestion" ||
                  finding.category ===
                    "suggestion" ||
                  finding.ai_suggestion === true
              ).length
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
    };
  }, [requirements]);

  /*
   * ---------------------------------------------------------
   * PAGE
   * ---------------------------------------------------------
   */

  return (
    <AppShell active="projects">
      <div className="rule-engine-page">

        <RuleEngineHeader
          project={project}
          projectLoading={projectLoading}
        />

        <section className="rule-engine-heading">
          <div className="rule-engine-heading-icon">
            <ShieldCheck size={27} />
          </div>

          <div>
            <h2>Requirements</h2>

            <p>
              AI extracted requirements from your
              uploaded documents. Review, validate
              and manage them.
            </p>
          </div>
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
                Running rule engine...
              </p>
            </div>
          )}

          {!loading && error && (
            <div className="rule-state rule-error">
              <p>{error}</p>

              <button
                type="button"
                className="rule-retry-button"
                onClick={fetchRequirements}
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
                  No extracted requirements found
                  for this project.
                </p>
              </div>
            )}

          {!loading &&
            !error &&
            requirements.length > 0 && (
              <RuleTable
                requirements={requirements}
                search={search}
                onSearchChange={setSearch}
                onSelectRule={setSelectedRule}
              />
            )}

        </main>

        {selectedRule && (
          <RuleDetailsModal
            requirement={selectedRule}
            onClose={() =>
              setSelectedRule(null)
            }
          />
        )}

      </div>
    </AppShell>
  );
}

export default RuleEnginePage;