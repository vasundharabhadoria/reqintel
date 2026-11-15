import { hasOAuthFlow } from "../features/auth/pkce";

// Where should a return from Supabase (OAuth, email confirmation, password
// recovery) be handled? Supabase falls back to the project's Site URL when the
// exact redirect URL is not on its allow-list, so the user can land on "/" or
// "/login" with the code/tokens attached. Instead of losing them, forward to
// the page that knows what to do. Query/hash are passed through untouched.
export function returnTarget({ pathname, search, hash }) {
  if (pathname === "/auth/callback" || pathname === "/reset-password") {
    return null;
  }

  const query = new URLSearchParams(search);
  const fragment = new URLSearchParams(hash.replace(/^#/, ""));

  if (fragment.get("type") === "recovery" && fragment.get("access_token")) {
    return `/reset-password${hash}`;
  }

  const confirmation = ["signup", "email", "invite"].includes(fragment.get("type"));
  const fragmentError = fragment.has("error_code") || fragment.has("error");

  if (confirmation || fragmentError) {
    return `/auth/callback${hash}`;
  }

  // An OAuth code/error is only ours if THIS browser started the flow.
  const oauthReturn =
    query.has("code") || query.has("error") || query.has("error_code");

  if (oauthReturn && hasOAuthFlow()) {
    return `/auth/callback${search}`;
  }

  return null;
}
