import { apiRequest } from "./client";

export function listProjects({ status, search } = {}) {
  const params = new URLSearchParams();

  if (status && status !== "all") {
    params.set("status", status);
  }

  if (search) {
    params.set("search", search);
  }

  const query = params.toString();

  return apiRequest(`/api/v1/projects${query ? `?${query}` : ""}`, {
    method: "GET",
  });
}

export function getProject(projectId) {
  return apiRequest(`/api/v1/projects/${projectId}`, {
    method: "GET",
  });
}

export function createProject({
  name,
  clientName,
  projectType,
  description,
}) {
  return apiRequest("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify({
      name,
      client_name: clientName || null,
      project_type: projectType || null,
      description: description || null,
    }),
  });
}

export function updateProject(
  projectId,
  { name, clientName, projectType, description }
) {
  return apiRequest(`/api/v1/projects/${projectId}`, {
    method: "PUT",
    body: JSON.stringify({
      name,
      client_name: clientName || null,
      project_type: projectType || null,
      description: description || null,
    }),
  });
}

export function archiveProject(projectId) {
  return apiRequest(`/api/v1/projects/${projectId}`, {
    method: "DELETE",
  });
}

export function updateProjectStatus(projectId, status) {
  return apiRequest(`/api/v1/projects/${projectId}/status`, {
    method: "PATCH",
    body: JSON.stringify({
      status,
    }),
  });
}