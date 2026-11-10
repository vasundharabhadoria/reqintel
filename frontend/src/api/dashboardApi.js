import { apiRequest } from "./client";

export function getDashboardSummary({ activityLimit = 10 } = {}) {
  return apiRequest(
    `/api/v1/dashboard/summary?activity_limit=${encodeURIComponent(activityLimit)}`,
    { method: "GET" }
  );
}