import { apiRequest } from "./client";

export function listReports({ projectId, reportFormat } = {}) {
  const params = new URLSearchParams();

  if (projectId && projectId !== "all") {
    params.set("project_id", projectId);
  }

  if (reportFormat && reportFormat !== "all") {
    params.set("report_format", reportFormat);
  }

  const query = params.toString();

  return apiRequest(`/api/v1/reports${query ? `?${query}` : ""}`, {
    method: "GET",
  });
}

export function generateReport({ projectId, reportFormat }) {
  return apiRequest("/api/v1/reports", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      report_format: reportFormat,
    }),
  });
}

export function getReport(reportId) {
  return apiRequest(`/api/v1/reports/${reportId}`, {
    method: "GET",
  });
}

export function downloadReportFile(reportId) {
  return apiRequest(`/api/v1/reports/${reportId}/download`, {
    method: "GET",
    responseType: "blob",
  });
}

export function deleteReport(reportId) {
  return apiRequest(`/api/v1/reports/${reportId}`, {
    method: "DELETE",
  });
}