import { apiRequest } from "./client";

export function getProfile() {
  return apiRequest("/api/v1/auth/profile", { method: "GET" });
}

export function updateProfile(fullName) {
  return apiRequest("/api/v1/auth/profile", {
    method: "PATCH",
    body: JSON.stringify({ full_name: fullName }),
  });
}

// The account to delete is always the one in the access token: no user id is
// ever sent. `password` is only needed for accounts with an email identity.
export function deleteAccount({ password } = {}) {
  return apiRequest("/api/v1/auth/account", {
    method: "DELETE",
    body: JSON.stringify({
      confirmation: "DELETE",
      ...(password ? { password } : {}),
    }),
  });
}
