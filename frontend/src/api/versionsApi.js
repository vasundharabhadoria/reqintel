import { apiRequest } from "./client";

export function listRepositoryVersions(
  projectId,
  { search = "", page = 1, pageSize = 10 } = {}
) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });

  if (search.trim()) {
    params.set("search", search.trim());
  }

  return apiRequest(
    `/api/v1/projects/${projectId}/versions?${params.toString()}`,
    { method: "GET" }
  );
}

export function getRepositoryVersion(projectId, versionId) {
  return apiRequest(
    `/api/v1/projects/${projectId}/versions/${versionId}`,
    { method: "GET" }
  );
}
