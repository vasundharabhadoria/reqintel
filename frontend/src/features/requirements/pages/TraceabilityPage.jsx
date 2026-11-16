import { useNavigate, useParams } from "react-router-dom";
import AppShell from "../../../components/layout/AppShell";
import RuleEngineHeader from "../../rule-engine/components/RuleEngineHeader";
import { getProject } from "../../../api/projectApi";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  GitBranch,
  Search,
  Plus,
  Eye,
  X,
  Link2,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  RefreshCw,
  FileText,
    Activity,
  Loader2,
  Sparkles,

} from "lucide-react";

import {
  listRequirements,
  getRequirement,
  listTraceabilityLinks,
  listProjectTraceabilityLinks,
  createTraceabilityLink,
  listTraceabilitySuggestions,
  analyzeTraceabilityImpact,
  getTraceabilityImpact,
} from "../../../api/requirementsApi";

import { useToast } from "../../../hooks/useToast";
import { useCurrentRepositoryVersion } from "../../versions/hooks/useCurrentRepositoryVersion";
import "../styles/traceability.css";

const LINK_TYPES = [
  { value: "depends_on", label: "Depends on" },
  { value: "derived_from", label: "Derived from" },
  { value: "relates_to", label: "Relates to" },
  { value: "duplicates", label: "Duplicates" },
  { value: "conflicts_with", label: "Conflicts with" },
  { value: "functional", label: "Functional" },
  { value: "non_functional", label: "Non-Functional" },
  { value: "security", label: "Security" },
];

function getArray(response) {
  if (Array.isArray(response)) return response;
  if (!response || typeof response !== "object") return [];

  if (Array.isArray(response.items)) return response.items;
  if (Array.isArray(response.requirements)) return response.requirements;
  if (Array.isArray(response.links)) return response.links;

  if (response.data && typeof response.data === "object") {
    return getArray(response.data);
  }

  return [];
}

function getRequirementId(requirement) {
  const id =
    requirement?.id ??
    requirement?.requirement_id ??
    requirement?.uuid;

  return id == null ? "" : String(id);
}

function getRequirementCode(requirement, index = 0) {
  return (
    requirement?.requirement_code ||
    requirement?.requirement_key ||
    requirement?.requirement_number ||
    requirement?.external_id ||
    requirement?.code ||
    `REQ-${String(index + 1).padStart(3, "0")}`
  );
}

function getRequirementText(requirement) {
  const candidates = [
    requirement?.current_requirement_text,
    requirement?.currentRequirementText,
    requirement?.requirement_text,
    requirement?.requirementText,
    requirement?.description,
    requirement?.text,
  ];

  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }

  return "No requirement description available.";
}

function getLinkSourceId(link) {
  const value =
    link?.source_requirement_id ??
    link?.sourceRequirementId ??
    link?.source_requirement?.id ??
    link?.source_id;

  return value == null ? "" : String(value);
}

function getLinkTargetId(link) {
  const value =
    link?.target_requirement_id ??
    link?.targetRequirementId ??
    link?.target_requirement?.id ??
    link?.target_id;

  return value == null ? "" : String(value);
}

function getLinkType(link) {
  return (
    link?.link_type ||
    link?.linkType ||
    link?.relationship_type ||
    "relates_to"
  );
}

function getErrorMessage(error) {
  return (
    error?.response?.data?.detail ||
    error?.message ||
    "Something went wrong. Please try again."
  );
}

function getImpactLevel(requirement, links = []) {
  // Missing Link requirements should not receive an impact level
  if (links.length === 0) {
    return "Not set";
  }

  const text = getRequirementText(requirement).toLowerCase();

  const highImpactKeywords = [
    "security",
    "authentication",
    "authorization",
    "encryption",
    "payment",
    "financial",
    "personal data",
    "privacy",
    "access control",
    "data breach",
  ];

  const hasCriticalContent = highImpactKeywords.some((keyword) =>
    text.includes(keyword)
  );

  const linkTypes = links.map((link) =>
    String(getLinkType(link)).toLowerCase()
  );

  const hasCriticalRelationship = linkTypes.some((type) =>
    ["security", "conflicts_with"].includes(type)
  );

  // HIGH: Critical requirement or significant dependency impact
  if (
    hasCriticalContent ||
    hasCriticalRelationship ||
    links.length >= 3
  ) {
    return "High";
  }

  // MEDIUM: Important dependency relationships
  if (
    links.length >= 2 ||
    linkTypes.some((type) =>
      ["depends_on", "derived_from"].includes(type)
    )
  ) {
    return "Medium";
  }

  // LOW: Limited, ordinary relationships
  return "Low";
}
function getOverallImpactLevel(items = [], hasLinks = true) {
  if (!hasLinks) return "Not set";
  if (items.length === 0) return "Not evaluated";

  const priority = {
    low: 1,
    medium: 2,
    high: 3,
    critical: 4,
  };

  const highestRisk = items.reduce((highest, item) => {
    const risk = String(item.risk_level || "").toLowerCase();

    return (priority[risk] || 0) > (priority[highest] || 0)
      ? risk
      : highest;
  }, "");

  if (!highestRisk) return "Not evaluated";

  return highestRisk.charAt(0).toUpperCase() + highestRisk.slice(1);
}
function getImpactReason(requirement, links = []) {
  if (links.length === 0) {
    return "Impact evaluation is unavailable because no traceability links exist.";
  }

  const text = getRequirementText(requirement).toLowerCase();

  const highImpactKeywords = [
    "security",
    "authentication",
    "authorization",
    "encryption",
    "payment",
    "financial",
    "personal data",
    "privacy",
    "access control",
    "data breach",
  ];

  const criticalKeywords = highImpactKeywords.filter((keyword) =>
    text.includes(keyword)
  );

  const linkTypes = links.map((link) =>
    String(getLinkType(link)).toLowerCase()
  );

  if (criticalKeywords.length > 0) {
    return `High impact due to critical requirement content: ${criticalKeywords.join(", ")}.`;
  }

  if (linkTypes.some((type) => ["security", "conflicts_with"].includes(type))) {
    return "High impact due to security-sensitive or conflicting traceability relationships.";
  }

  if (links.length >= 3) {
    return `High impact because this requirement has ${links.length} direct traceability relationships.`;
  }

  if (links.length >= 2) {
    return `Medium impact because this requirement has ${links.length} direct traceability relationships.`;
  }

  if (linkTypes.some((type) => ["depends_on", "derived_from"].includes(type))) {
    return "Medium impact because this requirement has dependency or derivation relationships.";
  }

  return "Low impact because this requirement has limited, ordinary traceability relationships.";
}
function isChangedSinceVersion(requirement) {
  return Boolean(
    requirement?.changed_since_last_version ??
    requirement?.changedSinceLastVersion ??
    requirement?.is_changed ??
    requirement?.has_changed ??
    requirement?.changed_since_version
  );
}

function TraceabilityPanel({ projectId: suppliedProjectId }) {
  const { projectId: routeProjectId } = useParams();
  const projectId = suppliedProjectId || routeProjectId;

  const navigate = useNavigate();
  const { showToast } = useToast();

  const [project, setProject] = useState(null);
  const [projectLoading, setProjectLoading] = useState(true);
  
  useEffect(() => {
  let cancelled = false;

  async function loadProject() {
    try {
      console.log("LOAD PROJECT START", projectId);

      const data = await getProject(projectId);
      console.log("PROJECT DATA:", JSON.stringify(data, null, 2));
      if (!cancelled) {
        setProject(data);
      }
    } catch (error) {
      console.error("Failed to load project header:", error);
    } finally {
      if (!cancelled) {
        setProjectLoading(false);
      }
    }
  }

  if (projectId) {
    loadProject();
  } else {
    setProjectLoading(false);
  }

  return () => {
    cancelled = true;
  };
}, [projectId]);
  const [requirements, setRequirements] = useState([]);
  const computedRepositoryVersion = useMemo(() => {
  const versions = requirements
    .map((requirement) =>
      Number(requirement.current_version_number)
    )
    .filter(
      (version) =>
        Number.isFinite(version) && version > 0
    );

  return versions.length > 0
    ? Math.max(...versions)
    : null;
}, [requirements]);
  const repositoryVersion = useCurrentRepositoryVersion(
    projectId,
    computedRepositoryVersion,
    requirements
  );
  const [links, setLinks] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [impactFilter, setImpactFilter] = useState("all");

  const [selectedRequirement, setSelectedRequirement] =
    useState(null);
const [impactItems, setImpactItems] = useState([]);
const [impactByRequirement, setImpactByRequirement] = useState({});
const [impactLoading, setImpactLoading] = useState(false);
const [impactAnalyzing, setImpactAnalyzing] = useState(false);
const [impactMessage, setImpactMessage] = useState("");
const [impactCompleted, setImpactCompleted] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [sourceRequirementId, setSourceRequirementId] =
    useState("");
  const [targetRequirementId, setTargetRequirementId] =
    useState("");
    const [linkMode, setLinkMode] = useState("single");
const [relatedRequirementIds, setRelatedRequirementIds] = useState([]);
  const [parentRequirementIds, setParentRequirementIds] = useState([]);
const [childRequirementIds, setChildRequirementIds] = useState([]);
const [linkType, setLinkType] = useState("depends_on");
  const [saving, setSaving] = useState(false);

  const fetchTraceability = useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
 const response = await listRequirements(projectId);
const requirementItems = getArray(response);

const detailedRequirements = await Promise.all(
  requirementItems.map(async (requirement) => {
    const requirementId = getRequirementId(requirement);

    if (!requirementId) {
      return requirement;
    }

    try {
      const detailResponse = await getRequirement(
        projectId,
        requirementId
      );

      const detail =
        detailResponse?.requirement ??
        detailResponse?.data?.requirement ??
        detailResponse?.data ??
        detailResponse;

      return {
        ...requirement,
        ...(detail && typeof detail === "object" ? detail : {}),
      };
    } catch (error) {
      console.error(
        `Failed to fetch requirement ${requirementId}:`,
        error
      );

      return requirement;
    }
  })
);

setRequirements(detailedRequirements);
const impactEntries = await Promise.all(
  detailedRequirements.map(async (requirement) => {
    const id = getRequirementId(requirement);

    try {
      const response = await getTraceabilityImpact(projectId, id);
      return [id, getArray(response)];
    } catch {
      return [id, []];
    }
  })
);

setImpactByRequirement(
  Object.fromEntries(impactEntries)
);
      
const linkResponse = await listProjectTraceabilityLinks(projectId);
const linkItems = getArray(linkResponse);

const uniqueLinks = new Map();

linkItems.forEach((link) => {
  const sourceId = getLinkSourceId(link);
  const targetId = getLinkTargetId(link);

  if (!sourceId || !targetId) return;

  const type = getLinkType(link);
  const key = `${sourceId}:${targetId}:${type}`;

  uniqueLinks.set(key, {
    ...link,
    source_requirement_id: sourceId,
    target_requirement_id: targetId,
    link_type: type,
  });
});

setLinks(Array.from(uniqueLinks.values()));
setSuggestionsLoading(true);

try {
  const suggestionResponse =
    await listTraceabilitySuggestions(projectId);

  setSuggestions(getArray(suggestionResponse));
} catch (error) {
  console.error("Failed to fetch traceability suggestions:", error);
  setSuggestions([]);
} finally {
  setSuggestionsLoading(false);
}

    } catch (error) {
      setLoadError(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [projectId, showToast]);

  useEffect(() => {
    fetchTraceability();
  }, [fetchTraceability]);
useEffect(() => {
  if (!selectedRequirement || !projectId) {
    setImpactItems([]);
    setImpactMessage("");
    return;
  }

  let cancelled = false;

  async function loadImpact() {
    setImpactLoading(true);
    setImpactMessage("");

    try {
      const response = await getTraceabilityImpact(
        projectId,
        getRequirementId(selectedRequirement)
      );

     if (!cancelled) {
  const savedItems = getArray(response);
  setImpactItems(savedItems);
  setImpactCompleted(savedItems.length > 0);

  if (response?.message) {
    setImpactMessage(response.message);
  }
}
    } catch (error) {
      if (!cancelled) {
        setImpactItems([]);
        setImpactMessage(getErrorMessage(error));
      }
    } finally {
      if (!cancelled) setImpactLoading(false);
    }
  }

  loadImpact();

  return () => {
    cancelled = true;
  };
}, [selectedRequirement, projectId]);
  const requirementMap = useMemo(() => {
    return new Map(
      requirements
        .filter((item) => getRequirementId(item))
        .map((item) => [getRequirementId(item), item])
    );
  }, [requirements]);

  const requirementIndexMap = useMemo(() => {
    return new Map(
      requirements.map((item, index) => [
        getRequirementId(item),
        index,
      ])
    );
  }, [requirements]);

  const getCodeById = useCallback(
    (id) => {
      const normalizedId = id == null ? "" : String(id);
      const requirement = requirementMap.get(normalizedId);

      if (!requirement) {
        return normalizedId || "—";
      }

      return getRequirementCode(
        requirement,
        requirementIndexMap.get(normalizedId) ?? 0
      );
    },
    [requirementMap, requirementIndexMap]
  );

  const getCounts = useCallback(
    (requirementId) => {
      const id =
        requirementId == null ? "" : String(requirementId);

      return {
        parents: links.filter(
          (link) => link.target_requirement_id === id
        ),
        children: links.filter(
          (link) => link.source_requirement_id === id
        ),
      };
    },
    [links]
  );
  const handleAcceptSuggestion = async (suggestion) => {
  const sourceId = String(suggestion.source_requirement_id);
  const targetId = String(suggestion.target_requirement_id);

  if (!sourceId || !targetId || sourceId === targetId) {
    showToast("Invalid traceability suggestion.", "error");
    return;
  }

  setSaving(true);

  try {
   await createTraceabilityLink(
  projectId,
  sourceId,
  {
    sourceRequirementId: sourceId,
    targetRequirementId: targetId,
    linkType: suggestion.link_type || "relates_to",
  }
);
    showToast("Suggested traceability link created.", "success");

    await fetchTraceability();
  } catch (error) {
    showToast(getErrorMessage(error), "error");
  } finally {
    setSaving(false);
  }
};

const handleRejectSuggestion = (suggestion) => {
  const sourceId = String(suggestion.source_requirement_id);
  const targetId = String(suggestion.target_requirement_id);

  setSuggestions((current) =>
    current.filter(
      (item) =>
        !(
          String(item.source_requirement_id) === sourceId &&
          String(item.target_requirement_id) === targetId
        )
    )
  );

  showToast("Suggestion dismissed.", "success");
};
  const rows = useMemo(() => {
    const allRows = requirements.map((requirement, index) => {
      const id = getRequirementId(requirement);

      const parents = links.filter(
        (link) => link.target_requirement_id === id
      );

      const children = links.filter(
        (link) => link.source_requirement_id === id
      );

            const relatedLinks = [...parents, ...children];
      const linked = relatedLinks.length > 0;

     const traceStatus = linked ? "Complete" : "Missing Link";

      return {
        id,
        code: getRequirementCode(requirement, index),
        text: getRequirementText(requirement),
        requirement,
        parents,
        children,
        relatedLinks,
        linked,
        traceStatus,
        impact: getOverallImpactLevel(
  impactByRequirement[id] || [],
  linked
),
        changed: isChangedSinceVersion(requirement),
      };
    });

    const query = search.trim().toLowerCase();

    return allRows.filter((row) => {
      const matchesSearch =
        !query ||
        row.code.toLowerCase().includes(query) ||
        row.text.toLowerCase().includes(query);

    const matchesStatus =
  statusFilter === "all" ||
  (statusFilter === "complete" &&
    row.traceStatus === "Complete") ||
  (statusFilter === "missing" &&
    row.traceStatus === "Missing Link");
      const matchesImpact =
        impactFilter === "all" ||
        row.impact.toLowerCase() === impactFilter;

      return matchesSearch && matchesStatus && matchesImpact;
    });
  }, [
    requirements,
    links,
    search,
    statusFilter,
    impactFilter,
     impactFilter,
  impactByRequirement,
  ]);

  const stats = useMemo(() => {
    const linkedIds = new Set();

    links.forEach((link) => {
      linkedIds.add(link.source_requirement_id);
      linkedIds.add(link.target_requirement_id);
    });

    const highImpact = requirements.filter((requirement) => {
  const id = getRequirementId(requirement);

  const related = links.filter(
    (link) =>
      link.source_requirement_id === id ||
      link.target_requirement_id === id
  );

  return (
    getOverallImpactLevel(
      impactByRequirement[id] || [],
      related.length > 0
    ).toLowerCase() === "high"
  );
}).length;
    return {
      totalLinks: links.length,
      fullyLinked: requirements.filter((item) =>
        linkedIds.has(getRequirementId(item))
      ).length,
      missing: requirements.filter(
        (item) =>
          getRequirementId(item) &&
          !linkedIds.has(getRequirementId(item))
      ).length,
      highImpact,
      changed: requirements.filter(isChangedSinceVersion).length,
      sourceDocuments: new Set(
        requirements
          .map(
            (item) =>
              item?.source_document_name ??
              item?.source_document?.name ??
              item?.source_document?.filename ??
              item?.document_name ??
              item?.document_filename ??
              item?.file_name
          )
          .filter(Boolean)
          .map((item) =>
            typeof item === "object"
              ? item.name || item.filename || item.title
              : String(item)
          )
          .filter(Boolean)
      ).size,
    };
}, [requirements, links, impactByRequirement]);

  const clearFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setImpactFilter("all");
  };

const handleCreateLink = async (event) => {
  event.preventDefault();

  if (
    parentRequirementIds.length === 0 &&
    childRequirementIds.length === 0
  ) {
    showToast(
      "Select at least one parent or child requirement.",
      "error"
    );
    return;
  }

  const pairs = [
    ...parentRequirementIds.map((id) => ({
      sourceId: id,
      targetId: selectedId,
    })),
    ...childRequirementIds.map((id) => ({
      sourceId: selectedId,
      targetId: id,
    })),
  ];

  if (pairs.some(({ sourceId, targetId }) => sourceId === targetId)) {
    showToast("A requirement cannot be linked to itself.", "error");
    return;
  }

  const existingPairs = new Set(
    links.map(
      (link) =>
        `${String(link.source_requirement_id)}-${String(link.target_requirement_id)}`
    )
  );

  const newPairs = pairs.filter(
    ({ sourceId, targetId }) =>
      !existingPairs.has(`${String(sourceId)}-${String(targetId)}`)
  );

  if (newPairs.length === 0) {
    showToast("These traceability links already exist.", "error");
    return;
  }

  setSaving(true);

  try {
    for (const { sourceId, targetId } of newPairs) {
      await createTraceabilityLink(projectId, sourceId, {
        sourceRequirementId: sourceId,
        targetRequirementId: targetId,
        linkType,
      });
    }

    showToast(
      `${newPairs.length} traceability link(s) created successfully.`,
      "success"
    );

    setShowCreateForm(false);
    setParentRequirementIds([]);
    setChildRequirementIds([]);
    setRelatedRequirementIds([]);
    setLinkMode("single");

    await fetchTraceability();
  } catch (error) {
    showToast(getErrorMessage(error), "error");
    await fetchTraceability();
  } finally {
    setSaving(false);
  }
};
const handleAnalyzeImpact = async () => {
  if (!selectedRequirement) return;

  const requirementId = getRequirementId(selectedRequirement);
  const relatedLinks = [
    ...selectedCounts.parents,
    ...selectedCounts.children,
  ];

  if (relatedLinks.length === 0) {
    setImpactItems([]);
    setImpactMessage("No traceability links found. Impact level is Not set.");
    return;
  }

  setImpactAnalyzing(true);
  setImpactMessage("");

  try {
    const response = await analyzeTraceabilityImpact(
      projectId,
      requirementId
    );
const updatedItems = getArray(response);

setImpactItems(updatedItems);
setImpactByRequirement((current) => ({
  ...current,
  [requirementId]: updatedItems,
}));
setImpactCompleted(true);
    setImpactMessage(
      response?.message ||
      (response?.saved > 0
        ? `${response.saved} impact record(s) saved successfully.`
        : "No impact records were generated.")
    );

    showToast("Impact analysis completed.", "success");
  } catch (error) {
    setImpactMessage(getErrorMessage(error));
    showToast(getErrorMessage(error), "error");
  } finally {
    setImpactAnalyzing(false);
  }
};
  const getLinkLabel = (value) =>
    LINK_TYPES.find((item) => item.value === value)?.label ||
    String(value || "Unknown").replaceAll("_", " ");

  const formatConnectedRequirements = (items, direction) => {
    if (!items.length) {
      return <span className="trace-no-link">—</span>;
    }

    return (
      <div className="trace-connected-list">
        {items.map((link, index) => {
          const id =
            direction === "parent"
              ? link.source_requirement_id
              : link.target_requirement_id;

          const connected = requirementMap.get(String(id));

          return (
            <span
              className="trace-connected-item"
              key={`${id}-${getLinkType(link)}-${index}`}
              title={getRequirementText(connected || {})}
            >
              {getCodeById(id)}
            </span>
          );
        })}
      </div>
    );
  };

  const selectedId = getRequirementId(selectedRequirement);
  const selectedCounts = selectedRequirement
    ? getCounts(selectedId)
    : { parents: [], children: [] };

  const selectedImpact = selectedRequirement
    ? getImpactLevel(selectedRequirement, [
        ...selectedCounts.parents,
        ...selectedCounts.children,
      ])
    : "Not set";
    const selectedTraceComplete =
  selectedCounts.parents.length > 0 ||
  selectedCounts.children.length > 0;

const missingParent = selectedCounts.parents.length === 0;
const missingChild = selectedCounts.children.length === 0;
 const selectedSuggestions = suggestions.filter(
  (suggestion) =>
    String(suggestion.source_requirement_id) === selectedId ||
    String(suggestion.target_requirement_id) === selectedId
);
  return (
     <AppShell active="projects">
    <RuleEngineHeader
      project={project}
      projectLoading={projectLoading}
      repositoryVersion={repositoryVersion}
      activeTab="traceability"
    />
    <section className="traceability-page traceability-redesign">
      <div className="trace-page-heading">
  <div>
    <div className="trace-heading-title-row">
  <h2>Traceability</h2>
</div>

    <p>
      View relationships between requirements and related
      artifacts across the repository.
    </p>
  </div>
</div>

      {loadError && (
        <div className="trace-error">
          <AlertCircle size={18} />
          <span>{loadError}</span>
          <button type="button" onClick={fetchTraceability}>
            Retry
          </button>
        </div>
      )}

      <div className="trace-stat-grid trace-stat-grid-six">
        <article className="trace-stat-card">
          <span className="trace-stat-icon trace-blue">
            <GitBranch size={23} />
          </span>
          <div>
            <h3>{loading ? "—" : stats.totalLinks}</h3>
            <p>Total Trace Links</p>
          </div>
        </article>

        <article className="trace-stat-card">
          <span className="trace-stat-icon trace-green">
            <CheckCircle2 size={23} />
          </span>
          <div>
            <h3>{loading ? "—" : stats.fullyLinked}</h3>
            <p>Fully Linked Requirements</p>
          </div>
        </article>

        <article className="trace-stat-card">
          <span className="trace-stat-icon trace-orange">
            <Link2 size={23} />
          </span>
          <div>
            <h3>{loading ? "—" : stats.missing}</h3>
            <p>Missing Links</p>
          </div>
        </article>

        <article className="trace-stat-card">
          <span className="trace-stat-icon trace-red">
            <TrendingUp size={23} />
          </span>
          <div>
            <h3>{loading ? "—" : stats.highImpact}</h3>
            <p>High Impact Requirements</p>
          </div>
        </article>

        <article className="trace-stat-card">
          <span className="trace-stat-icon trace-teal">
            <FileText size={23} />
          </span>
          <div>
            <h3>{loading ? "—" : stats.sourceDocuments}</h3>
            <p>Source Documents</p>
          </div>
        </article>
      </div>

      <div className="trace-content-card trace-matrix-card">
        <div className="trace-filter-toolbar">
          <label className="trace-search trace-search-wide">
            <Search size={19} />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search requirements by ID or keywords..."
              aria-label="Search requirements by ID or keywords"
            />
          </label>

          <label className="trace-filter-field">
            <span>Trace Status</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="all">All</option>
              <option value="complete">Complete</option>
              <option value="missing">Missing Link</option>
            </select>
          </label>

          <label className="trace-filter-field">
            <span>Impact Level</span>
            <select
              value={impactFilter}
              onChange={(event) => setImpactFilter(event.target.value)}
            >
              <option value="all">All</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="not set">Not set</option>
            </select>
          </label>

          <button
            type="button"
            className="trace-clear-filters"
            onClick={clearFilters}
          >
            <RefreshCw size={15} />
            Clear Filters
          </button>
        </div>

        {loading ? (
          <div className="trace-empty-state">
            <RefreshCw className="trace-spinning" size={24} />
            <p>Loading traceability data...</p>
          </div>
        ) : rows.length === 0 ? (
          <div className="trace-empty-state">
            <GitBranch size={30} />
            <h3>
              {requirements.length
                ? "No matching requirements"
                : "No requirements found"}
            </h3>
            <p>
              {requirements.length
                ? "Try changing your search or filters."
                : "Add requirements to this project to begin mapping relationships."}
            </p>
          </div>
        ) : (
          <div className="trace-table-wrap trace-wide-table-wrap">
            <table className="trace-table trace-wide-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Requirement ID</th>
                  <th>Requirement Description</th>
                  <th>Parent Requirement</th>
                  <th>Child Requirement(s)</th>
                  <th>Trace Status</th>
                  <th>Impact Level</th>
                  <th>Action</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((row, index) => (
                  <tr key={row.id || row.code}>
                    <td>{index + 1}</td>

                    <td>
                      <span className="trace-req-code">
                        {row.code}
                      </span>
                    </td>

                    <td>
                      <p className="trace-requirement-text trace-requirement-full">
                        {row.text}
                      </p>
                    </td>

                    <td>
                      {formatConnectedRequirements(
                        row.parents,
                        "parent"
                      )}
                    </td>

                    <td>
                      {formatConnectedRequirements(
                        row.children,
                        "child"
                      )}
                    </td>

                    <td>
                      <span
                        className={`trace-status ${
                          row.linked ? "is-linked" : "is-unlinked"
                        }`}
                      >
                        {row.linked ? (
                          <CheckCircle2 size={14} />
                        ) : (
                          <AlertCircle size={14} />
                        )}
                        {row.traceStatus}
                      </span>
                    </td>

                    <td>
                      <span
                        className={`trace-impact trace-impact-${row.impact
                          .toLowerCase()
                          .replaceAll(" ", "-")}`}
                      >
                        {row.impact}
                      </span>
                    </td>

                    <td>
                      <button
                        type="button"
                        className="trace-view-btn"
                        onClick={() =>
                          setSelectedRequirement(row.requirement)
                        }
                        aria-label={`View ${row.code}`}
                      >
                        <Eye size={15} />
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="trace-table-footer">
          <span>
            Showing {rows.length} of {requirements.length} requirements
          </span>

          <span className="trace-legend">
            <span>
              <i className="legend-dot legend-green" />
              Complete — Fully linked
            </span>
            <span>
              <i className="legend-dot legend-orange" />
              Missing Link — Requires linking
            </span>
            <span>
              <i className="legend-dot legend-yellow" />
              High Impact — Significant impact
            </span>
          </span>
        </div>
      </div>

      {showCreateForm && (
        <div
          className="trace-modal-backdrop"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget &&
              !saving
            ) {
              setShowCreateForm(false);
            }
          }}
        >
          <section
            className="trace-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="trace-create-title"
          >
            <div className="trace-modal-header">
              <div>
                <h3 id="trace-create-title">
                  Create Traceability Link
                </h3>
                <p>Connect two requirements in this project.</p>
              </div>

              <button
                type="button"
                className="trace-icon-btn"
                onClick={() => setShowCreateForm(false)}
                disabled={saving}
                aria-label="Close dialog"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateLink}>
              {linkMode === "parent" && (
          <label className="trace-form-field">
  <span>Parent Requirements</span>

  <details className="trace-multi-dropdown">
    <summary>
      {parentRequirementIds.length > 0
        ? `${parentRequirementIds.length} parent(s) selected`
        : "None (No Parent)"}
    </summary>

    <div className="trace-multi-dropdown-options">
      <label>
        <input
          type="checkbox"
          checked={parentRequirementIds.length === 0}
          onChange={() => setParentRequirementIds([])}
        />
        None (No Parent)
      </label>

      {requirements
        .filter(getRequirementId)
        .filter((item) => getRequirementId(item) !== selectedId)
        .map((item, index) => {
          const id = getRequirementId(item);

          return (
            <label key={id}>
              <input
                type="checkbox"
                checked={parentRequirementIds.includes(id)}
                onChange={(event) => {
                  setParentRequirementIds((current) =>
                    event.target.checked
                      ? [...current, id]
                      : current.filter((value) => value !== id)
                  );
                }}
              />
              {getRequirementCode(item, index)} — {getRequirementText(item)}
            </label>
          );
        })}
    </div>
  </details>
</label>
)}
{linkMode === "child" && (
<label className="trace-form-field">
  <span>Child Requirements</span>

  <details className="trace-multi-dropdown">
    <summary>
      {childRequirementIds.length > 0
        ? `${childRequirementIds.length} child(ren) selected`
        : "None (No Child)"}
    </summary>

    <div className="trace-multi-dropdown-options">
      <label>
        <input
          type="checkbox"
          checked={childRequirementIds.length === 0}
          onChange={() => setChildRequirementIds([])}
        />
        None (No Child)
      </label>

      {requirements
        .filter(getRequirementId)
        .filter((item) => getRequirementId(item) !== selectedId)
        .map((item, index) => {
          const id = getRequirementId(item);

          return (
            <label key={id}>
              <input
                type="checkbox"
                checked={childRequirementIds.includes(id)}
                onChange={(event) => {
                  setChildRequirementIds((current) =>
                    event.target.checked
                      ? [...current, id]
                      : current.filter((value) => value !== id)
                  );
                }}
              />
              {getRequirementCode(item, index)} — {getRequirementText(item)}
            </label>
          );
        })}
    </div>
  </details>
</label>
          )}   

              <label className="trace-form-field">
                <span>Relationship Type</span>
                <select
                  value={linkType}
                  onChange={(event) => setLinkType(event.target.value)}
                  required
                >
                  {LINK_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </label>

              <div className="trace-modal-footer">
                <button
                  type="button"
                  className="trace-btn trace-btn-secondary"
                  onClick={() => setShowCreateForm(false)}
                  disabled={saving}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="trace-btn trace-btn-primary"
                  disabled={
  saving ||
  (parentRequirementIds.length === 0 &&
    childRequirementIds.length === 0)
}
                >
                  <Plus size={16} />
                  {saving ? "Creating..." : "Create Link"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      
{selectedRequirement && (
  <div
    className="trace-drawer-backdrop"
    onMouseDown={(event) => {
      if (event.target === event.currentTarget) {
        setSelectedRequirement(null);
      }
    }}
  >
    <aside
      className="trace-drawer trace-drawer-reference"
      role="dialog"
      aria-modal="true"
      aria-label="Traceability details"
    >
      <div className="trace-drawer-header trace-reference-header">
        <div>
          <h3>Traceability Details</h3>
          <div className="trace-reference-identity">
            <div>
              <span>Requirement ID</span>
              <strong>
                {getRequirementCode(
                  selectedRequirement,
                  requirementIndexMap.get(selectedId) ?? 0
                )}
              </strong>
            </div>
            <div>
  <span>Repository Version</span>
  <strong>
    {repositoryVersion != null
      ? `Version ${repositoryVersion}`
      : "Not available"}
  </strong>
</div>
            <div>
              <span>Trace Status</span>
              <span
                className={`trace-status ${
                  selectedCounts.parents.length +
                    selectedCounts.children.length > 0
                    ? "is-linked"
                    : "is-unlinked"
                }`}
              >
                {selectedCounts.parents.length +
                  selectedCounts.children.length > 0 ? (
                  <CheckCircle2 size={13} />
                ) : (
                  <AlertCircle size={13} />
                )}
                {selectedCounts.parents.length +
                  selectedCounts.children.length > 0
                  ? "Complete"
                  : "Missing Link"}
              </span>
            </div>
          </div>
        </div>

        <button
          type="button"
          className="trace-icon-btn"
          onClick={() => setSelectedRequirement(null)}
          aria-label="Close details"
        >
          <X size={20} />
        </button>
      </div>

      <div className="trace-drawer-body trace-reference-body">
        <section className="trace-reference-section">
          <h4>1. Requirement</h4>
          <p>{getRequirementText(selectedRequirement)}</p>
        </section>
        {!selectedTraceComplete && (
  <section className="trace-reference-section trace-missing-section">
    <h4>2. Missing Relationships</h4>

    <div className="trace-missing-alert">
      <AlertCircle size={20} />
      <div>
        <strong>Traceability is incomplete</strong>
        <p>
          This requirement needs additional relationships
          to complete its traceability mapping.
        </p>
      </div>
    </div>

    <div className="trace-missing-list">
      {missingParent && (
        <div className="trace-missing-item">
          <div>
            <strong>Parent Requirement</strong>
            <span>Missing parent relationship</span>
          </div>

          <button
            type="button"
            onClick={() => {
  setLinkMode("parent");
  setRelatedRequirementIds([]);
  setSourceRequirementId("");
  setTargetRequirementId(selectedId);
  setLinkType("depends_on");
  setShowCreateForm(true);
}}
          >
            <Plus size={14} />
            Add Parent
          </button>
        </div>
      )}

      {missingChild && (
        <div className="trace-missing-item">
          <div>
            <strong>Child Requirement</strong>
            <span>Missing child relationship</span>
          </div>

          <button
            type="button"
onClick={() => {
  setLinkMode("child");
  setRelatedRequirementIds([]);
  setSourceRequirementId(selectedId);
  setTargetRequirementId("");
  setLinkType("depends_on");
  setShowCreateForm(true);
}}          
>
            <Plus size={14} />
            Add Child
          </button>
        </div>
      )}
    </div>
  </section>
)}

        {(() => {
          const req = selectedRequirement;
    const sourceName =
  req.source_document_name ||
  req.source_document?.name ||
  req.source_document?.filename ||
  req.document_name ||
  req.document_filename ||
  req.file_name ||
  null;

const documentVersion =
  req.document_version ||
  req.source_document?.version ||
  null;

const extractedAt =
  req.extracted_at ||
  req.extraction_date ||
  null;

          return (
            <section className="trace-reference-section">
  <h4>2. Source Information</h4>

  <div className="trace-source-grid">
    <div>
      <span>Source</span>
      <strong
  className={`trace-source-value ${
    sourceName ? "document-source" : "manual-source"
  }`}
>
  {sourceName || "Manual Entry"}
</strong>
    </div>

    {documentVersion && (
      <div>
        <span>Document Version</span>
        <strong>{documentVersion}</strong>
      </div>
    )}

    {extractedAt && (
      <div>
        <span>Extracted On</span>
        <strong>{String(extractedAt)}</strong>
      </div>
    )}
  </div>
</section>
          );
        })()}

        <section className="trace-reference-section">
          <h4>3. Parent Links ({selectedCounts.parents.length})</h4>
          {selectedCounts.parents.length === 0 ? (
            <p className="trace-muted">No parent links recorded.</p>
          ) : (
            <div className="trace-reference-chips">
              {selectedCounts.parents.map((link, index) => (
                <span key={`${link.source_requirement_id}-${index}`}>
                  {getCodeById(link.source_requirement_id)}
                </span>
              ))}
            </div>
          )}
        </section>

        <section className="trace-reference-section">
          <h4>4. Child Links ({selectedCounts.children.length})</h4>
          {selectedCounts.children.length === 0 ? (
            <p className="trace-muted">No child links recorded.</p>
          ) : (
            <div className="trace-reference-chips">
              {selectedCounts.children.map((link, index) => (
                <span key={`${link.target_requirement_id}-${index}`}>
                  {getCodeById(link.target_requirement_id)}
                </span>
              ))}
            </div>
          )}
        </section>

        <section className="trace-reference-section">
          <h4>5. Linked Artifacts Summary</h4>
          <div className="trace-artifact-summary">
            <div><span>Parent Links</span><strong>{selectedCounts.parents.length}</strong></div>
            <div><span>Child Links</span><strong>{selectedCounts.children.length}</strong></div>
            <div><span>Source Documents</span><strong>{selectedRequirement.source_document_name || selectedRequirement.document_name || selectedRequirement.file_name || selectedRequirement.source_document?.name || selectedRequirement.source_document?.filename ? 1 : 0}</strong></div>
           
            <div className="trace-artifact-total">
              <span>Total Requirement Links</span>
              <strong>{selectedCounts.parents.length + selectedCounts.children.length}</strong>
            </div>
          </div>
        </section>

        <section className="trace-reference-section">
          <h4>6. Linked Artifacts Details</h4>

          <details className="trace-artifact-accordion" open>
            <summary>Parent Links ({selectedCounts.parents.length})</summary>
            {selectedCounts.parents.length === 0 ? (
              <p className="trace-muted">No parent links recorded.</p>
            ) : (
              selectedCounts.parents.map((link, index) => (
                <div className="trace-artifact-row" key={`${link.source_requirement_id}-${index}`}>
                  <strong>{getCodeById(link.source_requirement_id)}</strong>
                  <span>{getLinkLabel(getLinkType(link))}</span>
                </div>
              ))
            )}
          </details>

          <details className="trace-artifact-accordion" open>
            <summary>Child Links ({selectedCounts.children.length})</summary>
            {selectedCounts.children.length === 0 ? (
              <p className="trace-muted">No child links recorded.</p>
            ) : (
              selectedCounts.children.map((link, index) => (
                <div className="trace-artifact-row" key={`${link.target_requirement_id}-${index}`}>
                  <strong>{getCodeById(link.target_requirement_id)}</strong>
                  <span>{getLinkLabel(getLinkType(link))}</span>
                </div>
              ))
            )}
          </details>

          
        </section>



<section className="trace-reference-section">
  <div className="impact-section-heading">
    <div>
      <h4>7. Impact Analysis</h4>
      <p>AI-assisted assessment of linked requirement dependencies.</p>
    </div>
    <span className={`impact-evaluation-status ${
      !selectedTraceComplete
        ? "is-unavailable"
        : impactItems.length > 0
        ? "is-evaluated"
        : "is-pending"
    }`}>
      {!selectedTraceComplete
        ? "Missing links"
        : impactItems.length > 0
        ? "Evaluated"
        : "Not evaluated"}
    </span>
  </div>

  <div className="impact-assessment-card">
    <div className="impact-assessment-top">
      <div className="impact-assessment-icon">
        <Activity size={21} />
      </div>
      <div className="impact-assessment-info">
        <strong>Requirement Impact Assessment</strong>
        <span>
          {selectedCounts.parents.length + selectedCounts.children.length}
          {" "}linked dependencies
        </span>
      </div>
      <button
        type="button"
        className="impact-analyze-button"
        onClick={handleAnalyzeImpact}
       disabled={
  impactAnalyzing ||
  impactLoading ||
  !selectedTraceComplete ||
  impactCompleted
}
      >
        {impactAnalyzing ? (
          <>
            <Loader2 size={15} className="impact-spinner" />
            Analyzing
          </>
        ) : (
          <>
            <Sparkles size={15} />
            Analyze Impact
          </>
        )}
      </button>
    </div>

    {impactLoading ? (
      <div className="impact-empty-state">
        <Loader2 size={22} className="impact-spinner" />
        <strong>Loading assessment</strong>
        <span>Retrieving saved impact analysis...</span>
      </div>
    ) : !selectedTraceComplete ? (
      <div className="impact-empty-state">
        <AlertCircle size={25} />
        <strong>Impact assessment unavailable</strong>
        <span>
          Create the required traceability links before evaluating impact.
        </span>
        <span className="impact-not-set">Impact level: Not set</span>
      </div>
    ) : impactItems.length > 0 ? (
      <div className="impact-results-list">
        {impactItems.map((item) => {
          const affected = requirementMap.get(
            String(item.affected_requirement_id)
          );

          const level = String(item.risk_level || "Not set").toLowerCase();

          return (
            <div className="impact-result-card" key={item.id}>
              <div className="impact-result-header">
                <div>
                  <span className="impact-result-label">
                    Affected requirement
                  </span>
                  <strong>
                    {affected
                      ? getRequirementCode(
                          affected,
                          requirementIndexMap.get(
                            String(item.affected_requirement_id)
                          ) ?? 0
                        )
                      : "Affected Requirement"}
                  </strong>
                </div>

                <span className={`impact-risk-badge risk-${level}`}>
                  {level.charAt(0).toUpperCase() + level.slice(1)}
                </span>
              </div>

              <p>{item.impact_description}</p>

              <div className="impact-result-footer">
                <span>
                  <CheckCircle2 size={13} />
                  AI evaluated
                </span>
                <span>Saved in database</span>
              </div>
            </div>
          );
        })}
      </div>
    ) : (
      <div className="impact-empty-state">
        <Sparkles size={25} />
        <strong>Not evaluated yet</strong>
        <span>
          Run AI analysis to identify the potential impact on linked
          requirements.
        </span>
      </div>
    )}

    {impactMessage && impactItems.length > 0 && (
      <p className="impact-feedback">{impactMessage}</p>
    )}
  </div>
</section>



        <section className="trace-reference-section">
          <h4>8. Rule Engine Findings</h4>
          <div className="trace-findings-list">
            <div>
              {selectedCounts.parents.length > 0 ? (
                <CheckCircle2 size={15} />
              ) : (
                <AlertCircle size={15} />
              )}
              <span>Parent link {selectedCounts.parents.length > 0 ? "exists" : "not recorded"}</span>
            </div>
            <div>
              {selectedCounts.children.length > 0 ? (
                <CheckCircle2 size={15} />
              ) : (
                <AlertCircle size={15} />
              )}
              <span>Child link {selectedCounts.children.length > 0 ? "exists" : "not recorded"}</span>
            </div>
            <div>
              {selectedRequirement.source_document_name ||
              selectedRequirement.document_name ||
              selectedRequirement.file_name ||
              selectedRequirement.source_document?.name ||
              selectedRequirement.source_document?.filename ? (
                <CheckCircle2 size={15} />
              ) : (
                <AlertCircle size={15} />
              )}
              <span>Source mapping {selectedRequirement.source_document_name ||
              selectedRequirement.document_name ||
              selectedRequirement.file_name ||
              selectedRequirement.source_document?.name ||
              selectedRequirement.source_document?.filename ? "available" : "not available"}</span>
            </div>
          </div>
        </section>

          {!selectedTraceComplete && selectedSuggestions.length > 0 && (
          <section className="trace-reference-section">
            <h4>Suggested Links</h4>
            {selectedSuggestions.map((suggestion, index) => {
              const sourceId = String(suggestion.source_requirement_id);
              const targetId = String(suggestion.target_requirement_id);
              return (
                <div className="trace-link-item" key={`${sourceId}-${targetId}-${index}`}>
                  <div>
                    <strong>
                      {getCodeById(sourceId)} → {getCodeById(targetId)}
                    </strong>
                    <span>Match: {suggestion.match_score ?? "N/A"}</span>
                  </div>
                  <p>{suggestion.reason || "Suggested relationship between requirements."}</p>
                  <div className="trace-suggestion-actions">
                    <button type="button" className="trace-accept-button" disabled={saving} onClick={() => handleAcceptSuggestion(suggestion)}>
                      <CheckCircle2 size={14} /> Accept
                    </button>
                    <button type="button" className="trace-reject-button" disabled={saving} onClick={() => handleRejectSuggestion(suggestion)}>
                      <X size={14} /> Reject
                    </button>
                  </div>
                </div>
              );
            })}
          </section>
        )}

        <button
          type="button"
          className="trace-btn trace-btn-secondary trace-reference-close"
          onClick={() => setSelectedRequirement(null)}
        >
          Close
        </button>
      </div>
    </aside>
  </div>
)}

    </section>
      </AppShell>
  );
}

export default TraceabilityPanel;
