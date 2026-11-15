import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowLeft, CheckCircle2, Mail } from "lucide-react";

import { forgotPassword } from "../../../api/authApi";
import AuthLayout from "../components/AuthLayout";
import { useCooldown } from "../useCooldown";
import { isValidEmail } from "../validation";
import "../styles/auth.css";

function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const cooldown = useCooldown(60);

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");
    setMessage("");

    const cleanEmail = email.trim();

    if (!isValidEmail(cleanEmail)) {
      setError("Enter a valid email address.");
      return;
    }

    setLoading(true);

    try {
      // Same answer whether or not the account exists (no enumeration).
      const result = await forgotPassword(cleanEmail);

      setMessage(result.message);
      cooldown.start();
    } catch (err) {
      setError(err.message);
      cooldown.start(err.retryAfter);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout>
      <div className="auth-card">
        <h1>Forgot your password?</h1>
        <p className="auth-card-subtitle">
          Enter your email and we'll send you a link to reset it.
        </p>

        {message && (
          <div className="auth-success-box" role="status">
            <CheckCircle2
              size={16}
              style={{ marginRight: 6, verticalAlign: "text-bottom" }}
            />
            {message}
          </div>
        )}

        {error && (
          <div className="auth-error-box" role="alert">
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

          <button
            type="submit"
            className="auth-submit-button"
            disabled={loading || cooldown.remaining > 0}
          >
            {loading
              ? "Sending..."
              : cooldown.remaining > 0
                ? `Send again in ${cooldown.remaining}s`
                : "Send reset link"}
          </button>
        </form>

        <p className="auth-footer">
          <Link to="/login">
            <ArrowLeft size={13} style={{ verticalAlign: "text-bottom" }} /> Back
            to login
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}

export default ForgotPasswordPage;
