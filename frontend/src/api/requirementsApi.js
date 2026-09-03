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
    headers: { "Content-Type": undefined },
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
  if (status && status !== "all") params.set("status", status);
  if (search) params.set("search", search);
  if (sourceId) params.set("source_id", sourceId);

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

export function createVersion(projectId, requirementId, { requirementText, changeSummary }) {
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