import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, Mail } from "lucide-react";

import { useAuth } from "../../../hooks/useAuth";
import AuthLayout from "../components/AuthLayout";
import PasswordInput from "../components/PasswordInput";
import "../styles/auth.css";

const REMEMBERED_EMAIL_KEY = "reqintel_remembered_email";

function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [email, setEmail] = useState(
    () => localStorage.getItem(REMEMBERED_EMAIL_KEY) || ""
  );
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(
    () => !!localStorage.getItem(REMEMBERED_EMAIL_KEY)
  );

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showForgotNote, setShowForgotNote] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");
    setLoading(true);

    try {
      const currentUser = await login(email, password);

      if (rememberMe) {
        localStorage.setItem(REMEMBERED_EMAIL_KEY, email);
      } else {
        localStorage.removeItem(REMEMBERED_EMAIL_KEY);
      }

      if (currentUser.role === "admin") {
        navigate("/master-module");
      } else {
        navigate("/dashboard");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout>
      <div className="auth-card">
        <h1>Welcome Back!</h1>
        <p className="auth-card-subtitle">
          Login to your account to continue
        </p>

        {error && (
          <div className="auth-error-box">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
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

            <button
              type="button"
              className="auth-link-button"
              onClick={() => setShowForgotNote((current) => !current)}
            >
              Forgot Password?
            </button>
          </div>

          {showForgotNote && (
            <p className="auth-inline-note">
              Password reset isn't available yet. Please contact your
              administrator.
            </p>
          )}

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

        <button
          type="button"
          className="auth-oauth-button"
          disabled
          title="Google sign-in coming soon"
        >
          <span className="auth-google-icon">G</span>
          Continue with Google
        </button>

        <p className="auth-footer">
          Don't have an account? <Link to="/register">Sign Up</Link>
        </p>
      </div>
    </AuthLayout>
  );
}

export default LoginPage;