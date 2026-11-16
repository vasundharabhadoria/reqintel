import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound, LogOut, Pencil, ShieldCheck, Trash2, UserRound } from "lucide-react";

import { deleteAccount, getProfile, updateProfile } from "../../../api/profileApi";
import AppShell from "../../../components/layout/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import DeleteAccountModal from "../components/DeleteAccountModal";
import {
  FULL_NAME_MAX_LENGTH,
  formatDate,
  providerLabel,
  roleLabel,
  validateFullName,
} from "../profileFormat";
import "../styles/profile.css";

const ACCOUNT_DELETED_NOTICE =
  "Your account and all of its data have been permanently deleted.";

function InfoRow({ label, children, hint }) {
  return (
    <div className="profile-row">
      <dt>{label}</dt>
      <dd>
        {children}
        {hint && <span className="profile-hint">{hint}</span>}
      </dd>
    </div>
  );
}

function ProfilePage() {
  const navigate = useNavigate();
  const { logout, endSession } = useAuth();

  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);

  const [signingOut, setSigningOut] = useState(false);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await getProfile();

        if (!cancelled) setProfile(data);
      } catch (err) {
        if (!cancelled) setLoadError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  function retryLoad() {
    setLoadError("");
    setLoading(true);
    setReloadKey((key) => key + 1);
  }

  // ---- edit profile -------------------------------------------------

  function startEditing() {
    setName(profile.full_name);
    setSaveError("");
    setSaved(false);
    setEditing(true);
  }

  function cancelEditing() {
    setEditing(false);
    setSaveError("");
  }

  async function handleSave(event) {
    event.preventDefault();

    const problem = validateFullName(name);

    if (problem) {
      setSaveError(problem);
      return;
    }

    setSaving(true);
    setSaveError("");

    try {
      // Only the full name is ever sent: role, status, email and id are not
      // editable, and the server rejects any attempt to include them.
      setProfile(await updateProfile(name.trim().replace(/\s+/g, " ")));
      setSaved(true);
      setEditing(false);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  }

  // ---- sign out -----------------------------------------------------

  async function handleSignOut() {
    setSigningOut(true);
    await logout();
    // `replace` keeps the protected page out of the history stack.
    navigate("/login", { replace: true });
  }

  // ---- delete account -----------------------------------------------

  function openDelete() {
    setDeleteError(null);
    setDeleteOpen(true);
  }

  async function handleDelete({ password }) {
    setDeleting(true);
    setDeleteError(null);

    try {
      await deleteAccount({ password });
    } catch (err) {
      // Stay signed in with a clear message; nothing local is cleared.
      setDeleteError({ message: err.message, code: err.code });
      setDeleting(false);
      return;
    }

    // Both run in the same tick, so the router never sees "signed out on a
    // protected page" and the user lands on /login with the confirmation.
    endSession();
    navigate("/login", {
      replace: true,
      state: { notice: ACCOUNT_DELETED_NOTICE },
    });
  }

  async function signOutToReauthenticate() {
    setDeleteOpen(false);
    await handleSignOut();
  }

  // ---- render -------------------------------------------------------

  let body;

  if (loading) {
    body = <p className="profile-state">Loading your profile...</p>;
  } else if (loadError) {
    body = (
      <div className="profile-state">
        <div className="profile-alert profile-alert-error" role="alert">
          {loadError}
        </div>
        <button type="button" className="btn btn-secondary" onClick={retryLoad}>
          Try again
        </button>
      </div>
    );
  } else {
    const isPasswordAccount = profile.reauth_method === "password";

    body = (
      <>
        {/* ---------------- Personal information ---------------- */}
        <section className="profile-card" aria-labelledby="profile-personal">
          <div className="profile-card-header">
            <div className="profile-card-title">
              <UserRound size={18} />
              <h2 id="profile-personal">Personal information</h2>
            </div>

            {!editing && (
              <button type="button" className="btn btn-secondary btn-small" onClick={startEditing}>
                <Pencil size={14} />
                Edit Profile
              </button>
            )}
          </div>

          {saved && !editing && (
            <div className="profile-alert profile-alert-success" role="status">
              Profile updated successfully.
            </div>
          )}

          {editing ? (
            <form className="profile-form" onSubmit={handleSave} noValidate>
              {saveError && (
                <div className="profile-alert profile-alert-error" role="alert">
                  {saveError}
                </div>
              )}

              <div className="profile-field-group">
                <label className="profile-label" htmlFor="profile-full-name">
                  Full name
                </label>
                <input
                  id="profile-full-name"
                  className="profile-input"
                  type="text"
                  autoComplete="name"
                  autoFocus
                  maxLength={FULL_NAME_MAX_LENGTH + 20}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  disabled={saving}
                />
              </div>

              <div className="profile-field-group">
                <span className="profile-label">Email address</span>
                <p className="profile-readonly">{profile.email}</p>
                <span className="profile-hint">Your email address cannot be changed here.</span>
              </div>

              <div className="profile-actions">
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? "Saving..." : "Save changes"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={cancelEditing}
                  disabled={saving}
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <dl className="profile-list">
              <InfoRow label="Full name">{profile.full_name}</InfoRow>
              <InfoRow label="Email address" hint="Read-only">
                {profile.email}
              </InfoRow>
            </dl>
          )}
        </section>

        {/* ---------------- Account information ---------------- */}
        <section className="profile-card" aria-labelledby="profile-account">
          <div className="profile-card-header">
            <div className="profile-card-title">
              <ShieldCheck size={18} />
              <h2 id="profile-account">Account information</h2>
            </div>
          </div>

          <dl className="profile-list">
            <InfoRow label="Role">{roleLabel(profile.role)}</InfoRow>
            <InfoRow label="Account status">
              <span
                className={`profile-badge ${
                  profile.is_active ? "profile-badge-active" : "profile-badge-inactive"
                }`}
              >
                {profile.is_active ? "Active" : "Inactive"}
              </span>
            </InfoRow>
            <InfoRow label="Member since">{formatDate(profile.created_at)}</InfoRow>
            <InfoRow label="User ID">
              <code className="profile-code">{profile.id}</code>
            </InfoRow>
          </dl>
        </section>

        {/* ---------------- Security ---------------- */}
        <section className="profile-card" aria-labelledby="profile-security">
          <div className="profile-card-header">
            <div className="profile-card-title">
              <KeyRound size={18} />
              <h2 id="profile-security">Security</h2>
            </div>
          </div>

          <dl className="profile-list">
            <InfoRow label="Sign-in method">{providerLabel(profile.auth_provider)}</InfoRow>
            <InfoRow label="Password">
              {isPasswordAccount
                ? "To change your password, sign out and use “Forgot password?” on the sign-in page."
                : `Your password is managed by ${providerLabel(profile.auth_provider)}.`}
            </InfoRow>
            <InfoRow label="Session">
              <button
                type="button"
                className="btn btn-secondary btn-small"
                onClick={handleSignOut}
                disabled={signingOut}
              >
                <LogOut size={14} />
                {signingOut ? "Signing out..." : "Sign Out"}
              </button>
            </InfoRow>
          </dl>
        </section>

        {/* ---------------- Danger zone ---------------- */}
        <section className="profile-card profile-danger" aria-labelledby="profile-danger">
          <div className="profile-card-header">
            <div className="profile-card-title profile-danger-title">
              <Trash2 size={18} />
              <h2 id="profile-danger">Danger Zone</h2>
            </div>
          </div>

          <div className="profile-danger-body">
            <div>
              <strong>Delete account</strong>
              <p>
                Permanently delete your account and all projects, requirements,
                documents and reports you own. This cannot be undone.
              </p>
            </div>

            <button type="button" className="btn btn-danger" onClick={openDelete}>
              <Trash2 size={14} />
              Delete Account
            </button>
          </div>
        </section>

        {deleteOpen && (
          <DeleteAccountModal
            open
            profile={profile}
            submitting={deleting}
            error={deleteError}
            onClose={() => setDeleteOpen(false)}
            onConfirm={handleDelete}
            onSignOut={signOutToReauthenticate}
          />
        )}
      </>
    );
  }

  return (
    <AppShell active="profile">
      <div className="profile-page">
        <header className="profile-page-header">
          <h1>Profile</h1>
          <p>Manage your personal information, security and account.</p>
        </header>

        {body}
      </div>
    </AppShell>
  );
}

export default ProfilePage;
