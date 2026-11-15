import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Mail, MailCheck, User } from "lucide-react";

import { resendConfirmation } from "../../../api/authApi";
import { useAuth } from "../../../hooks/useAuth";
import AuthLayout from "../components/AuthLayout";
import OAuthButtons from "../components/OAuthButtons";
import PasswordChecklist from "../components/PasswordChecklist";
import PasswordInput from "../components/PasswordInput";
import { useCooldown } from "../useCooldown";
import {
  FULL_NAME_MAX_LENGTH,
  PASSWORD_MAX_LENGTH,
  fullNameError,
  isValidEmail,
  passwordError,
} from "../validation";
import "../styles/auth.css";

function RegisterPage() {
  const { register } = useAuth();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [agreedToTerms, setAgreedToTerms] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [submittedEmail, setSubmittedEmail] = useState("");
  const [resendMessage, setResendMessage] = useState("");
  const [resending, setResending] = useState(false);
  const cooldown = useCooldown(60);

  function validate() {
    const nameProblem = fullNameError(fullName);

    if (nameProblem) {
      return nameProblem;
    }

    if (!isValidEmail(email)) {
      return "Enter a valid email address.";
    }

    const passwordProblem = passwordError(password);

    if (passwordProblem) {
      return passwordProblem;
    }

    if (password !== confirmPassword) {
      return "Passwords do not match.";
    }

    if (!agreedToTerms) {
      return "You must agree to the Terms and Conditions.";
    }

    return "";
  }

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");

    const validationError = validate();

    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);

    try {
      // confirmPassword is intentionally never sent to the backend.
      await register(fullName.trim(), email.trim(), password);

      // Email confirmation is on: the account cannot sign in until the link
      // in the email is opened, so show a check-your-email state.
      setSubmittedEmail(email.trim());
      cooldown.start();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setResending(true);
    setResendMessage("");
    setError("");

    try {
      const result = await resendConfirmation(submittedEmail);

      setResendMessage(result.message);
      cooldown.start();
    } catch (err) {
      setError(err.message);
      cooldown.start(err.retryAfter);
    } finally {
      setResending(false);
    }
  }

  if (submittedEmail) {
    return (
      <AuthLayout>
        <div className="auth-card auth-card-centered">
          <MailCheck size={44} className="auth-state-icon" />

          <h1>Check your email</h1>

          <p className="auth-card-subtitle">
            If <strong>{submittedEmail}</strong> can be registered, we sent a
            confirmation link. Open it to activate your account, then sign in.
          </p>

          <p className="auth-card-subtitle">
            Can't find it? Check your spam or junk folder.
          </p>

          {error && (
            <div className="auth-error-box" role="alert">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {resendMessage && (
            <div className="auth-success-box" role="status">
              {resendMessage}
            </div>
          )}

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

          <p className="auth-footer">
            Wrong address? <button
              type="button"
              className="auth-link-button"
              onClick={() => setSubmittedEmail("")}
            >
              Go back
            </button>
            {" · "}
            <Link to="/login">Back to login</Link>
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div className="auth-card">
        <h1>Create Your Account</h1>
        <p className="auth-card-subtitle">Start using ReqIntel</p>

        {error && (
          <div className="auth-error-box" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div className="auth-field">
            <label htmlFor="fullName">Full Name</label>

            <div className="auth-input-wrapper">
              <User size={18} className="auth-input-icon" />

              <input
                id="fullName"
                name="fullName"
                type="text"
                placeholder="Enter your full name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                autoComplete="name"
                maxLength={FULL_NAME_MAX_LENGTH}
                required
              />
            </div>
          </div>

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
            placeholder="Create a password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            maxLength={PASSWORD_MAX_LENGTH}
          />

          <PasswordChecklist password={password} />

          <PasswordInput
            id="confirmPassword"
            label="Confirm Password"
            placeholder="Re-enter your password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            autoComplete="new-password"
          />

          <label className="auth-checkbox-row" style={{ marginBottom: 20 }}>
            <input
              type="checkbox"
              checked={agreedToTerms}
              onChange={(event) => setAgreedToTerms(event.target.checked)}
            />
            I agree to the Terms and Conditions
          </label>

          <button type="submit" className="auth-submit-button" disabled={loading}>
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <div className="auth-divider">or sign up with</div>

        <OAuthButtons disabled={loading} onError={setError} />

        <p className="auth-footer">
          Already have an account? <Link to="/login">Login</Link>
        </p>
      </div>
    </AuthLayout>
  );
}

export default RegisterPage;
