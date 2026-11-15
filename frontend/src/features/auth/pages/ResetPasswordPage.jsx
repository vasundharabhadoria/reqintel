import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, CheckCircle2, LinkIcon } from "lucide-react";

import { resetPassword } from "../../../api/authApi";
import AuthLayout from "../components/AuthLayout";
import PasswordChecklist from "../components/PasswordChecklist";
import PasswordInput from "../components/PasswordInput";
import { PASSWORD_MAX_LENGTH, passwordError } from "../validation";
import "../styles/auth.css";

// Supabase redirects here with the recovery session in the URL fragment
// (#access_token=...&type=recovery) or, for a bad/expired link, with
// #error=...&error_code=otp_expired.
function readRecoveryLink() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const token = params.get("access_token");

  return {
    accessToken: params.get("type") === "recovery" && token ? token : null,
    expired: params.get("error_code") === "otp_expired",
  };
}

function ResetPasswordPage() {
  const navigate = useNavigate();

  // Read once; the token then lives only in component state.
  const [link] = useState(readRecoveryLink);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  // Remove the token from the address bar and history right away.
  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search
      );
    }
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");

    const problem = passwordError(password);

    if (problem) {
      setError(problem);
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      await resetPassword(link.accessToken, password);
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <AuthLayout>
        <div className="auth-card auth-card-centered">
          <CheckCircle2 size={44} className="auth-state-icon" />

          <h1>Password updated</h1>

          <p className="auth-card-subtitle">
            Your password has been changed. Sign in with your new password.
          </p>

          <button
            type="button"
            className="auth-submit-button"
            onClick={() =>
              navigate("/login", {
                replace: true,
                state: { notice: "Password updated. You can now sign in." },
              })
            }
          >
            Go to login
          </button>
        </div>
      </AuthLayout>
    );
  }

  if (!link.accessToken) {
    return (
      <AuthLayout>
        <div className="auth-card auth-card-centered">
          <LinkIcon size={44} className="auth-state-icon" />

          <h1>{link.expired ? "This link has expired" : "Invalid reset link"}</h1>

          <p className="auth-card-subtitle">
            Password reset links can be used once and expire quickly. Request a
            new one to continue.
          </p>

          <Link to="/forgot-password" className="auth-submit-button auth-link-as-button">
            Request a new link
          </Link>

          <p className="auth-footer">
            <Link to="/login">Back to login</Link>
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div className="auth-card">
        <h1>Set a new password</h1>
        <p className="auth-card-subtitle">Choose a strong password you don't use elsewhere.</p>

        {error && (
          <div className="auth-error-box" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <PasswordInput
            id="password"
            label="New Password"
            placeholder="Create a new password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            maxLength={PASSWORD_MAX_LENGTH}
          />

          <PasswordChecklist password={password} />

          <PasswordInput
            id="confirmPassword"
            label="Confirm New Password"
            placeholder="Re-enter the new password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            autoComplete="new-password"
          />

          <button type="submit" className="auth-submit-button" disabled={loading}>
            {loading ? "Updating..." : "Update password"}
          </button>
        </form>
      </div>
    </AuthLayout>
  );
}

export default ResetPasswordPage;
