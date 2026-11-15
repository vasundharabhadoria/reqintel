import { apiRequest } from "./client";

function post(endpoint, body) {
  return apiRequest(endpoint, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function loginUser(email, password) {
  return post("/api/v1/auth/login", { email, password });
}

export function registerUser(fullName, email, password) {
  return post("/api/v1/auth/signup", {
    full_name: fullName,
    email,
    password,
  });
}

export function resendConfirmation(email) {
  return post("/api/v1/auth/resend-confirmation", { email });
}

export function forgotPassword(email) {
  return post("/api/v1/auth/forgot-password", { email });
}

export function resetPassword(accessToken, newPassword) {
  return post("/api/v1/auth/reset-password", {
    access_token: accessToken,
    new_password: newPassword,
  });
}

export function getOAuthUrl(provider, codeChallenge) {
  return apiRequest(
    `/api/v1/auth/oauth/${provider}/url?code_challenge=${encodeURIComponent(
      codeChallenge
    )}`,
    { method: "GET" }
  );
}

export function exchangeOAuthCode(code, codeVerifier) {
  return post("/api/v1/auth/oauth/exchange", {
    code,
    code_verifier: codeVerifier,
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
