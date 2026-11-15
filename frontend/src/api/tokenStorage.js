// Tokens live in localStorage when the user chose "Remember me" (survives a
// browser restart) and in sessionStorage otherwise (cleared when the browser
// closes). Reads check both so a session is found wherever it was stored.

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

function safe(getStore) {
  try {
    return getStore();
  } catch {
    // Storage can be unavailable (private mode, blocked cookies).
    return null;
  }
}

const session = () => safe(() => window.sessionStorage);
const local = () => safe(() => window.localStorage);

function read(key) {
  return session()?.getItem(key) ?? local()?.getItem(key) ?? null;
}

export function getAccessToken() {
  return read(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
  return read(REFRESH_TOKEN_KEY);
}

// True when the current session was stored with "Remember me".
export function isPersistentSession() {
  return local()?.getItem(REFRESH_TOKEN_KEY) != null;
}

/**
 * Store a token pair.
 *
 * `remember` picks the storage: true -> localStorage, false -> sessionStorage.
 * When it is omitted (token refresh) the pair stays in whichever storage the
 * session already uses, so refreshing never changes the user's choice.
 */
export function setTokens(
  { access_token, refresh_token },
  { remember } = {}
) {
  const persist = remember ?? isPersistentSession();
  const target = persist ? local() : session();
  const other = persist ? session() : local();

  if (!target) {
    return;
  }

  if (access_token) {
    target.setItem(ACCESS_TOKEN_KEY, access_token);
    other?.removeItem(ACCESS_TOKEN_KEY);
  }

  if (refresh_token) {
    target.setItem(REFRESH_TOKEN_KEY, refresh_token);
    other?.removeItem(REFRESH_TOKEN_KEY);
  }
}

export function clearTokens() {
  for (const store of [session(), local()]) {
    store?.removeItem(ACCESS_TOKEN_KEY);
    store?.removeItem(REFRESH_TOKEN_KEY);
  }
}

export const TOKEN_STORAGE_KEYS = {
  access: ACCESS_TOKEN_KEY,
  refresh: REFRESH_TOKEN_KEY,
};
