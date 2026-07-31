import { apiRequest } from "./client";

export function loginUser(email, password) {
  return apiRequest("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
    }),
  });
}

export function registerUser(fullName, email, password) {
  return apiRequest("/api/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify({
      full_name: fullName,
      email,
      password,
    }),
  });
}

export function getCurrentUser() {
  return apiRequest("/api/v1/auth/me", {
    method: "GET",
  });
}

export function logoutUser() {
  return apiRequest("/api/v1/auth/logout", {
    method: "POST",
  });
}