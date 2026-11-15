import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, CheckCircle2, Mail } from "lucide-react";

import { resendConfirmation } from "../../../api/authApi";
import { useAuth } from "../../../hooks/useAuth";
import { homePathForUser } from "../../../routes/homePath";
import AuthLayout from "../components/AuthLayout";
import OAuthButtons from "../components/OAuthButtons";
import PasswordInput from "../components/PasswordInput";
import { useCooldown } from "../useCooldown";
import { isValidEmail } from "../validation";
import "../styles/auth.css";

const REMEMBERED_EMAIL_KEY = "reqintel_remembered_email";

function readRememberedEmail() {
  try {
    return localStorage.getItem(REMEMBERED_EMAIL_KEY) || "";
  } catch {
    return "";
  }
}

function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const [email, setEmail] = useState(readRememberedEmail);
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(() => !!readRememberedEmail());

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(location.state?.notice || "");
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [resending, setResending] = useState(false);
  const cooldown = useCooldown(60);

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");
    setNotice("");
    setNeedsConfirmation(false);

    const cleanEmail = email.trim();

    if (!isValidEmail(cleanEmail)) {
      setError("Enter a valid email address.");
      return;
    }

    if (!password) {
      setError("Enter your password.");
      return;
    }

    setLoading(true);

    try {
      const currentUser = await login(cleanEmail, password, rememberMe);

      try {
        if (rememberMe) {
          localStorage.setItem(REMEMBERED_EMAIL_KEY, cleanEmail);
        } else {
          localStorage.removeItem(REMEMBERED_EMAIL_KEY);
        }
      } catch {
        // Remembering the email is a convenience only.
      }

      // Send the user back to the page they were trying to open, if any.
      const from = location.state?.from?.pathname;

      navigate(from && from !== "/login" ? from : homePathForUser(currentUser), {
        replace: true,
      });
    } catch (err) {
      if (err.code === "email_not_confirmed") {
        setNeedsConfirmation(true);
      }

      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setResending(true);
    setError("");

    try {
      const result = await resendConfirmation(email.trim());

      setNotice(result.message);
      setNeedsConfirmation(false);
      cooldown.start();
    } catch (err) {
      setError(err.message);
      cooldown.start(err.retryAfter);
    } finally {
      setResending(false);
    }
  }

  return (
    <AuthLayout>
      <div className="auth-card">
        <h1>Welcome Back!</h1>
        <p className="auth-card-subtitle">
          Login to your account to continue
        </p>

        {notice && (
          <div className="auth-success-box" role="status">
            <CheckCircle2
              size={16}
              style={{ marginRight: 6, verticalAlign: "text-bottom" }}
            />
            {notice}
          </div>
        )}

        {error && (
          <div className="auth-error-box" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {needsConfirmation && (
          <button
            type="button"
            className="auth-secondary-button"
            onClick={handleResend}
            disabled={resending || cooldown.remaining > 0}
          >
            {cooldown.remaining > 0
              ? `Resend available in ${cooldown.remaining}s`
              : resending
                ? "Sending..."
                : "Resend confirmation email"}
          </button>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div className="auth-field">
            <label htmlFor="email">Email Address</label>

            <div className="auth-input-wrapper">
              <Mail size={18} className="auth-input-icon" />

              <input
                id="email"
                name="email"
                type="email"
                placeholder="Enter your email address"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </div>
          </div>

          <PasswordInput
            id="password"
            label="Password"
            placeholder="Enter your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />

          <div className="auth-options-row">
            <label className="auth-checkbox-row">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(event) => setRememberMe(event.target.checked)}
              />
              Remember me
            </label>

            <Link to="/forgot-password" className="auth-link-button">
              Forgot Password?
            </Link>
          </div>

          <button
            type="submit"
            className="auth-submit-button"
            disabled={loading}
          >
            {loading ? (
              "Signing in..."
            ) : (
              <>
                Login <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        <div className="auth-divider">or continue with</div>

        <OAuthButtons
          remember={rememberMe}
          disabled={loading}
          onError={setError}
        />

        <p className="auth-footer">
          Don't have an account? <Link to="/register">Sign Up</Link>
        </p>
      </div>
    </AuthLayout>
  );
}

export default LoginPage;
