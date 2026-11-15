import { useEffect, useState } from "react";

import { getOAuthUrl } from "../../../api/authApi";
import {
  challengeFromVerifier,
  generateVerifier,
  saveOAuthFlow,
} from "../pkce";

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.5 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 6.9l7.1 5.5c4.2-3.9 6.6-9.6 6.6-16.9z" />
      <path fill="#FBBC05" d="M10.5 28.7a14.5 14.5 0 0 1 0-9.4l-7.9-6.1a24 24 0 0 0 0 21.6l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.1-5.5c-2 1.4-4.6 2.3-8.8 2.3-6.3 0-11.6-4-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true">
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"
      />
    </svg>
  );
}

const PROVIDERS = [
  { id: "google", label: "Continue with Google", Icon: GoogleIcon },
  { id: "github", label: "Continue with GitHub", Icon: GitHubIcon },
];

// Starts a PKCE sign-in. No client secret exists in the browser: the
// provider credentials are configured in Supabase only.
function OAuthButtons({ remember = false, disabled = false, onError }) {
  const [starting, setStarting] = useState(null);

  // After redirecting to the provider, the browser's Back button restores
  // this page from its back/forward cache WITH the "Redirecting..." state
  // frozen in, leaving both buttons disabled. Reset it when that happens.
  useEffect(() => {
    function handlePageShow(event) {
      if (event.persisted) {
        setStarting(null);
      }
    }

    window.addEventListener("pageshow", handlePageShow);

    return () => window.removeEventListener("pageshow", handlePageShow);
  }, []);

  async function start(provider) {
    setStarting(provider);

    try {
      const verifier = generateVerifier();
      const challenge = await challengeFromVerifier(verifier);
      const { url } = await getOAuthUrl(provider, challenge);

      saveOAuthFlow({ verifier, remember, provider });
      window.location.assign(url);
    } catch (err) {
      setStarting(null);
      onError?.(err.message || "Unable to start sign-in. Please try again.");
    }
  }

  return (
    <div className="auth-oauth-group">
      {PROVIDERS.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          className="auth-oauth-button"
          disabled={disabled || starting !== null}
          onClick={() => start(id)}
        >
          <Icon />
          {starting === id ? "Redirecting..." : label}
        </button>
      ))}
    </div>
  );
}

export default OAuthButtons;
