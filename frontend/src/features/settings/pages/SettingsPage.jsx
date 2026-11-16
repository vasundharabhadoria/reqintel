import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { KeyRound, LogOut, Mail, UserRound } from "lucide-react";

import { forgotPassword } from "../../../api/authApi";
import AppShell from "../../../components/layout/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import {
  clearProfileSummary,
  useProfileSummary,
} from "../../../hooks/useProfileSummary";
import { useCooldown } from "../../auth/useCooldown";
import { providerLabel, roleLabel } from "../../profile/profileFormat";
import "../../profile/styles/profile.css";

function Row({ label, children }) {
  return (
    <div className="profile-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

// Only settings the backend really supports live here: account overview,
// sign-in/password security and the current session. Nothing is shown that
// cannot be saved.
function SettingsPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const profile = useProfileSummary(user?.id);
  const cooldown = useCooldown(60);

  const [sending, setSending] = useState(false);
  const [resetMessage, setResetMessage] = useState("");
  const [resetError, setResetError] = useState("");
  const [signingOut, setSigningOut] = useState(false);

  const isPasswordAccount = profile?.reauth_method === "password";

  async function handleSendReset() {
    if (sending || cooldown.remaining > 0) return;

    setSending(true);
    setResetError("");
    setResetMessage("");

    try {
      const result = await forgotPassword(user.email);
      setResetMessage(result.message);
      cooldown.start();
    } catch (err) {
      setResetError(err.message);
      cooldown.start(err.retryAfter);
    } finally {
      setSending(false);
    }
  }

  async function handleSignOut() {
    if (signingOut) return;

    setSigningOut(true);

    try {
      await logout();
    } finally {
      clearProfileSummary();
      navigate("/login", { replace: true });
    }
  }

  return (
    <AppShell active="settings">
      <div className="profile-page">
        <header className="profile-page-header">
          <h1>Settings</h1>
          <p>Review your account, sign-in security and current session.</p>
        </header>

        <section className="profile-card" aria-labelledby="settings-account">
          <div className="profile-card-header">
            <div className="profile-card-title">
              <UserRound size={18} />
              <h2 id="settings-account">Account</h2>
            </div>
            <Link to="/profile" className="btn btn-secondary btn-small">
              Edit in My Profile
            </Link>
          </div>

          <dl className="profile-list">
            <Row label="Name">{profile ? profile.full_name : "Loading…"}</Row>
            <Row label="Email address">{user?.email}</Row>
            <Row label="Role">{roleLabel(user?.role)}</Row>
          </dl>
        </section>

        <section className="profile-card" aria-labelledby="settings-security">
          <div className="profile-card-header">
            <div className="profile-card-title">
              <KeyRound size={18} />
              <h2 id="settings-security">Security</h2>
            </div>
          </div>

          {resetMessage && (
            <div className="profile-alert profile-alert-success" role="status">
              {resetMessage}
            </div>
          )}
          {resetError && (
            <div className="profile-alert profile-alert-error" role="alert">
              {resetError}
            </div>
          )}

          <dl className="profile-list">
            <Row label="Sign-in method">
              {profile ? providerLabel(profile.auth_provider) : "Loading…"}
            </Row>
            <Row label="Password">
              {!profile ? (
                "Loading…"
              ) : isPasswordAccount ? (
                <button
                  type="button"
                  className="btn btn-secondary btn-small"
                  onClick={handleSendReset}
                  disabled={sending || cooldown.remaining > 0}
                >
                  <Mail size={14} />
                  {sending
                    ? "Sending..."
                    : cooldown.remaining > 0
                      ? `Resend in ${cooldown.remaining}s`
                      : "Email me a password reset link"}
                </button>
              ) : (
                `Your password is managed by ${providerLabel(profile.auth_provider)}.`
              )}
            </Row>
          </dl>
        </section>

        <section className="profile-card" aria-labelledby="settings-session">
          <div className="profile-card-header">
            <div className="profile-card-title">
              <LogOut size={18} />
              <h2 id="settings-session">Session</h2>
            </div>
          </div>

          <dl className="profile-list">
            <Row label="This device">
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={handleSignOut}
                disabled={signingOut}
              >
                <LogOut size={14} />
                {signingOut ? "Signing out..." : "Sign Out"}
              </button>
            </Row>
          </dl>
        </section>
      </div>
    </AppShell>
  );
}

export default SettingsPage;
