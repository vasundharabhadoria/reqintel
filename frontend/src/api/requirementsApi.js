import { apiRequest } from "./client";

export function listSources(projectId) {
  return apiRequest(`/api/v1/projects/${projectId}/requirements/sources`, {
    method: "GET",
  });
}

export function uploadSource(projectId, file) {
  const formData = new FormData();
  formData.append("file", file);

  // apiRequest always sets Content-Type: application/json; override it here
  // so the browser can set the multipart boundary itself.
  return apiRequest(`/api/v1/projects/${projectId}/requirements/sources/upload`, {
    method: "POST",
    body: formData,
  });
}

export function createManualRequirement(projectId, { title, requirementText }) {
  return apiRequest(`/api/v1/projects/${projectId}/requirements/sources/manual`, {
    method: "POST",
    body: JSON.stringify({
      title,
      requirement_text: requirementText,
    }),
  });
}

export function extractSourceText(projectId, sourceId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/sources/${sourceId}/extract`,
    { method: "POST" }
  );
}

export function extractRequirements(projectId, sourceId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/sources/${sourceId}/extract-requirements`,
    { method: "POST" }
  );
}

export function listRequirements(projectId, { status, search, sourceId } = {}) {
  const params = new URLSearchParams();

  if (status && status !== "all") {
    params.set("status", status);
  }

  if (search) {
    params.set("search", search);
  }

  if (sourceId) {
    params.set("source_id", sourceId);
  }

  const query = params.toString();

  return apiRequest(
    `/api/v1/projects/${projectId}/requirements${query ? `?${query}` : ""}`,
    { method: "GET" }
  );
}

export function getRequirement(projectId, requirementId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}`,
    { method: "GET" }
  );
}

export function listVersions(projectId, requirementId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/versions`,
    { method: "GET" }
  );
}

export function createVersion(
  projectId,
  requirementId,
  { requirementText, changeSummary }
) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/versions`,
    {
      method: "POST",
      body: JSON.stringify({
        requirement_text: requirementText,
        change_summary: changeSummary || null,
      }),
    }
  );
}

export function analyzeRequirements(projectId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/analyze`,
    {
      method: "POST",
    }
  );
}

export function getSavedProjectAnalysis(projectId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/analysis`,
    {
      method: "GET",
    }
  );
}

export function deleteSource(projectId, sourceId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/sources/${sourceId}`,
    { method: "DELETE" }
  );
}

export function getSourceFile(projectId, sourceId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/sources/${sourceId}/file`,
    { method: "GET", responseType: "blob" }
  );
}
export function acceptSuggestion(projectId, requirementId, suggestionId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/suggestions/${suggestionId}/accept`,
    { method: "POST" }
  );
}

export function rejectSuggestion(projectId, requirementId, suggestionId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/suggestions/${suggestionId}/reject`,
    { method: "POST" }
  );
}

export function approveRequirement(projectId, requirementId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/approve`,
    { method: "POST" }
  );
}

export function waiveIssue(projectId, requirementId, ruleName, reason = "") {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/waivers`,
    {
      method: "POST",
      body: JSON.stringify({ rule_name: ruleName, reason }),
    }
  );
}

export function removeIssueWaiver(projectId, requirementId, ruleName) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/waivers?rule_name=${encodeURIComponent(ruleName)}`,
    { method: "DELETE" }
  );
}

export function rejectRequirement(projectId, requirementId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/reject`,
    { method: "POST" }
  );
}

export function listTraceabilityLinks(projectId, requirementId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/traceability`,
    { method: "GET" }
  );
}
export function listProjectTraceabilityLinks(projectId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/traceability`,
    {
      method: "GET",
    }
  );
}


export function createTraceabilityLink(
  projectId,
  requirementId,
  { sourceRequirementId, targetRequirementId, linkType }
) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/traceability`,
    {
      method: "POST",
      body: JSON.stringify({
        source_requirement_id:
          sourceRequirementId || requirementId,
        target_requirement_id: targetRequirementId,
        link_type: linkType,
      }),
    }
  );
}

export function listTraceabilitySuggestions(projectId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/traceability/suggestions`
  );
}

export function analyzeTraceabilityImpact(projectId, requirementId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/impact/analyze`,
    {
      method: "POST",
    }
  );
}

export function getTraceabilityImpact(projectId, requirementId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/requirements/${requirementId}/impact`,
    {
      method: "GET",
    }
  );
}
