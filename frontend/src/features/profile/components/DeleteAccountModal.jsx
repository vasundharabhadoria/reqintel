import { useState } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";

import Modal from "../../../components/common/Modal";
import { providerLabel } from "../profileFormat";

const CONFIRM_WORD = "DELETE";

const DELETED_ITEMS = [
  "Your account, sign-in identity and profile",
  "All projects you own, including archived ones",
  "Uploaded requirement documents and extracted requirements, with every version",
  "Validation results, AI analysis, traceability links and change impact records",
  "Generated reports and all stored files",
];

function DeleteAccountModal({
  open,
  profile,
  submitting,
  error,
  onClose,
  onConfirm,
  onSignOut,
}) {
  const [typed, setTyped] = useState("");
  const [password, setPassword] = useState("");

  // The parent mounts this dialog only while it is open, so the typed word
  // and password always start empty: a previous confirmation never carries over.

  if (!profile) return null;

  const needsPassword = profile.reauth_method === "password";
  const canDelete =
    typed === CONFIRM_WORD && (!needsPassword || password.length > 0) && !submitting;

  function handleClose() {
    if (!submitting) onClose();
  }

  function submit() {
    if (canDelete) onConfirm({ password: needsPassword ? password : undefined });
  }

  function handleKeyDown(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  }

  const needsFreshSignIn = error?.code === "reauth_required" && !needsPassword;

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Delete your account?"
      icon={<AlertTriangle size={20} color="#b91c1c" />}
      footer={
        <>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleClose}
            disabled={submitting}
          >
            Cancel
          </button>

          <button
            type="button"
            className="btn btn-danger"
            onClick={submit}
            disabled={!canDelete}
          >
            {submitting ? (
              "Deleting..."
            ) : (
              <>
                <Trash2 size={14} />
                Permanently Delete Account
              </>
            )}
          </button>
        </>
      }
    >
      {error && (
        <div className="profile-alert profile-alert-error" role="alert">
          {error.message}
          {needsFreshSignIn && (
            <button type="button" className="profile-link-button" onClick={onSignOut}>
              Sign out and sign in again
            </button>
          )}
        </div>
      )}

      <div className="profile-delete-warning">
        <AlertTriangle size={16} />
        <span>
          This action <strong>cannot be undone</strong>. Your account and its data
          are deleted permanently and cannot be recovered.
        </span>
      </div>

      <p className="profile-delete-text">The following will be permanently deleted:</p>

      <ul className="profile-delete-list">
        {DELETED_ITEMS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <p className="profile-delete-note">
        A minimal, anonymised audit trail of system activity is kept for record
        integrity. It is no longer linked to your account.
      </p>

      {needsPassword ? (
        <div className="profile-field-group">
          <label className="profile-label" htmlFor="delete-account-password">
            Confirm your password
          </label>
          <input
            id="delete-account-password"
            className="profile-input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={submitting}
          />
        </div>
      ) : (
        <p className="profile-delete-note">
          You signed in with {providerLabel(profile.auth_provider)}. For your
          security you must have signed in within the last 10 minutes. If deletion
          is refused, sign out, sign in again and retry.
        </p>
      )}

      <div className="profile-field-group">
        <label className="profile-label" htmlFor="delete-account-confirm">
          Type <strong>{CONFIRM_WORD}</strong> to confirm
        </label>
        <input
          id="delete-account-confirm"
          className="profile-input"
          type="text"
          autoComplete="off"
          autoFocus
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={submitting}
          placeholder={CONFIRM_WORD}
        />
      </div>
    </Modal>
  );
}

export default DeleteAccountModal;
