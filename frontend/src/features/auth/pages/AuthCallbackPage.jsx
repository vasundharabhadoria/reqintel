import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { useAuth } from "../../../hooks/useAuth";
import { homePathForUser } from "../../../routes/homePath";
import AuthLayout from "../components/AuthLayout";
import { takeOAuthFlow } from "../pkce";
import "../styles/auth.css";

// Only fixed, known messages are ever shown: error text in the URL can be
// written by anyone, so it is mapped, never displayed.
const EMAIL_PROBLEM =
  "We couldn't create your account from this provider. Make sure the provider account has a verified email address (for GitHub, a primary email, public or not), or sign up with email instead.";

const MESSAGES_BY_CODE = {
  access_denied:
    "Sign-in was cancelled. You can try again whenever you're ready.",
  otp_expired:
    "This confirmation link has expired. Sign in to request a new one.",
  bad_oauth_callback:
    "This sign-in attempt was invalid or expired. Please try again.",
  bad_oauth_state:
    "This sign-in attempt was invalid or expired. Please try again.",
  flow_state_not_found:
    "This sign-in attempt was invalid or expired. Please try again.",
  flow_state_expired:
    "This sign-in attempt expired. Please try again.",
  provider_email_needs_verification:
    "The email address at your provider isn't verified. Verify it there, then try again.",
  signup_disabled: "Sign-up is currently disabled.",
  email_exists:
    "This email is already registered with another sign-in method. Use your original method to sign in.",
  identity_already_exists:
    "This provider account is already linked to a different user.",
  user_banned: "This account has been deactivated.",
};

function messageForError(code, description = "") {
  if (MESSAGES_BY_CODE[code]) {
    return MESSAGES_BY_CODE[code];
  }

  if (
    /database error|saving new user|getting user email|email from external provider/i.test(
      description
    )
  ) {
    return EMAIL_PROBLEM;
  }

  return "Sign-in could not be completed. Please try again.";
}

// Works out what this page was opened for, from the URL alone.
function readCallback() {
  const query = new URLSearchParams(window.location.search);
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));

  const errorCode =
    query.get("error_code") || query.get("error") ||
    hash.get("error_code") || hash.get("error");

  if (errorCode) {
    return {
      status: "error",
      message: messageForError(
        errorCode,
        query.get("error_description") || hash.get("error_description") || ""
      ),
    };
  }

  // Email confirmation link (the tokens in the fragment are deliberately
  // discarded: the user signs in normally afterwards).
  const type = hash.get("type");

  if (type === "signup" || type === "email" || type === "invite") {
    return { status: "confirmed" };
  }

  const code = query.get("code");

  if (code) {
    return { status: "working", code };
  }

  return { status: "none" };
}

function AuthCallbackPage() {
  const navigate = useNavigate();
  const { loginWithOAuthCode } = useAuth();

  const [callback] = useState(readCallback);
  const [error, setError] = useState("");
  const started = useRef(false);

  const status = error ? "error" : callback.status;
  const message = error || callback.message;

  // Never leave the code, tokens or error details in the address bar/history.
  useEffect(() => {
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  useEffect(() => {
    if (callback.status === "none") {
      navigate("/login", { replace: true });
    }
  }, [callback.status, navigate]);

  useEffect(() => {
    if (callback.status !== "working" || started.current) {
      return;
    }

    started.current = true;

    async function finish() {
      // The stored flow holds the PKCE verifier and "Remember me" choice. It
      // can be used once, and only by the browser that started the flow.
      const flow = takeOAuthFlow();

      if (!flow?.verifier) {
        setError("This sign-in session has expired. Please start again.");
        return;
      }

      try {
        const user = await loginWithOAuthCode(
          callback.code,
          flow.verifier,
          !!flow.remember
        );

        navigate(homePathForUser(user), { replace: true });
      } catch (err) {
        setError(err.message);
      }
    }

    finish();
  }, [callback, loginWithOAuthCode, navigate]);

  return (
    <AuthLayout>
      <div className="auth-card auth-card-centered" aria-live="polite">
        {status === "working" && (
          <>
            <Loader2 size={44} className="auth-state-icon auth-spin" />
            <h1>Signing you in...</h1>
            <p className="auth-card-subtitle">One moment while we finish up.</p>
          </>
        )}

        {status === "confirmed" && (
          <>
            <CheckCircle2 size={44} className="auth-state-icon" />
            <h1>Email confirmed</h1>
            <p className="auth-card-subtitle">
              Your account is active. Sign in to continue.
            </p>
            <Link
              to="/login"
              state={{ notice: "Email confirmed. You can now sign in." }}
              className="auth-submit-button auth-link-as-button"
            >
              Go to login
            </Link>
          </>
        )}

        {status === "error" && (
          <>
            <AlertCircle size={44} className="auth-state-icon auth-state-error" />
            <h1>Couldn't sign you in</h1>
            <p className="auth-card-subtitle">{message}</p>
            <Link to="/login" className="auth-submit-button auth-link-as-button">
              Back to login
            </Link>
          </>
        )}
      </div>
    </AuthLayout>
  );
}

export default AuthCallbackPage;
