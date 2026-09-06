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
      console.error("Failed to load project:", err);
    } finally {
      setProjectLoading(false);
    }
  }, [projectId]);

  /*
   * ---------------------------------------------------------
   * LOAD REQUIREMENTS + SOURCES + RULE ENGINE RESULTS
   * ---------------------------------------------------------
   */

  const fetchRequirements = useCallback(async () => {
    if (!projectId) return;

    setLoading(true);
    setError("");

    try {
      const [
        requirementsData,
        analysisData,
        sourceData,
      ] = await Promise.all([
        listRequirements(projectId),
        analyzeRequirements(projectId),
        listSources(projectId),
      ]);

      const items = requirementsData?.items || [];
      const results = analysisData?.results || [];
      const sources = sourceData?.items || [];

      /*
       * Create source lookup by source ID
       */
      const sourcesById = new Map(
        sources.map((source) => [
          String(source.id),
          source,
        ])
      );

      /*
       * Create findings lookup by requirement ID
       */
      const findingsById = new Map(
        results.map((result) => [
          String(result.id),
          result.findings || [],
        ])
      );

      /*
       * Merge requirements with:
       * - findings
       * - source document name
       * - complete source information
       */
      const mergedRequirements = items.map(
        (requirement) => {
          const source = requirement.source_id
            ? sourcesById.get(
                String(requirement.source_id)
              )
            : null;

          /*
           * Keep the source URL if backend already provides one.
           *
           * Different backends may use different field names,
           * so we safely check the common possibilities.
           */
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
              findingsById.get(
                String(requirement.id)
              ) || [],

            source_document_name:
              requirement.source_document_name ||
              source?.original_filename ||
              source?.filename ||
              "—",

            source_document_url: sourceUrl,

            source_document: source,
          };
        }
      );

      setRequirements(mergedRequirements);
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
  }, [fetchProject, fetchRequirements]);

  /*
   * ---------------------------------------------------------
   * STATISTICS
   * ---------------------------------------------------------
   */

  const stats = useMemo(() => {
    const total = requirements.length;

    const pending = requirements.filter((req) => {
      const status = req.status?.toLowerCase();

      return (
        status === "pending" ||
        status === "pending review"
      );
    }).length;

    const approved = requirements.filter(
      (req) =>
        req.status?.toLowerCase() === "approved"
    ).length;

    const rejected = requirements.filter(
      (req) =>
        req.status?.toLowerCase() === "rejected"
    ).length;

    const issues = requirements.reduce(
      (count, requirement) => {
        return (
          count +
          (requirement.findings || []).filter(
            (finding) =>
              finding.passed === false
          ).length
        );
      },
      0
    );

    const aiSuggestions = requirements.reduce(
      (count, requirement) => {
        return (
          count +
          (requirement.findings || []).filter(
            (finding) =>
              finding.type === "suggestion" ||
              finding.category === "suggestion" ||
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

        {/* PROJECT HEADER */}

        <RuleEngineHeader
          project={project}
          projectLoading={projectLoading}
        />

        {/* REQUIREMENTS HEADING */}

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

        {/* MAIN CONTENT */}

        <main className="rule-engine-content">

          {/* STATS */}

          <RuleStatsCards stats={stats} />

          {/* LOADING */}

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

          {/* ERROR */}

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

          {/* EMPTY */}

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

          {/* TABLE */}

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

        {/* FINDINGS DRAWER */}

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