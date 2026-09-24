import { apiRequest } from "./client";

export function getCategories() {
  return apiRequest("/api/v1/master/categories", {
    method: "GET",
  });
}

export function createCategory(
  name,
  description,
  evaluationMode = "Issue"
) {
  return apiRequest("/api/v1/master/categories", {
    method: "POST",
    body: JSON.stringify({
      name,
      description,
      evaluation_mode: evaluationMode,
    }),
  });
}

export function updateCategory(categoryId, data) {
  return apiRequest(`/api/v1/master/categories/${categoryId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function deleteCategory(categoryId) {
  return apiRequest(`/api/v1/master/categories/${categoryId}`, {
    method: "DELETE",
  });
}

export function getRules(categoryId = null) {
  const endpoint = categoryId
    ? `/api/v1/master/rules?category_id=${encodeURIComponent(categoryId)}`
    : "/api/v1/master/rules";

  return apiRequest(endpoint, {
    method: "GET",
  });
}

export function createRule(data) {
  return apiRequest("/api/v1/master/rules", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateRule(ruleId, data) {
  return apiRequest(`/api/v1/master/rules/${ruleId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function deleteRule(ruleId) {
  return apiRequest(`/api/v1/master/rules/${ruleId}`, {
    method: "DELETE",
  });
}