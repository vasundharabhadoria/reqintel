// PKCE (RFC 7636) helpers for the Google / GitHub sign-in flow. The verifier
// never leaves this browser until the final code exchange, so an intercepted
// authorization code is useless to anyone else.

const OAUTH_STATE_KEY = "reqintel_oauth_flow";

function base64Url(bytes) {
  let binary = "";

  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }

  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function generateVerifier() {
  const bytes = new Uint8Array(48); // -> 64 URL-safe characters

  crypto.getRandomValues(bytes);

  return base64Url(bytes);
}

export async function challengeFromVerifier(verifier) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier)
  );

  return base64Url(new Uint8Array(digest));
}

export function saveOAuthFlow(flow) {
  sessionStorage.setItem(OAUTH_STATE_KEY, JSON.stringify(flow));
}

// True while a flow this browser started is waiting to be completed.
export function hasOAuthFlow() {
  try {
    return sessionStorage.getItem(OAUTH_STATE_KEY) !== null;
  } catch {
    return false;
  }
}

// Reads AND removes the stored flow: a flow can be completed only once.
export function takeOAuthFlow() {
  const raw = sessionStorage.getItem(OAUTH_STATE_KEY);

  sessionStorage.removeItem(OAUTH_STATE_KEY);

  try {
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
