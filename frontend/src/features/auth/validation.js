// Mirrors the backend rules in backend/auth/schemas.py. The backend is the
// authority; these checks only give instant feedback.

export const FULL_NAME_MAX_LENGTH = 150; // public.users.full_name is VARCHAR(150)
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function isValidEmail(email) {
  return EMAIL_PATTERN.test(String(email).trim());
}

export function passwordChecks(password) {
  return [
    {
      id: "length",
      label: `At least ${PASSWORD_MIN_LENGTH} characters`,
      passed: password.length >= PASSWORD_MIN_LENGTH,
    },
    { id: "lower", label: "A lowercase letter", passed: /[a-z]/.test(password) },
    { id: "upper", label: "An uppercase letter", passed: /[A-Z]/.test(password) },
    { id: "digit", label: "A number", passed: /\d/.test(password) },
  ];
}

// Returns the first unmet requirement as a sentence, or "" when valid.
export function passwordError(password) {
  if (password.length > PASSWORD_MAX_LENGTH) {
    return `Password must not exceed ${PASSWORD_MAX_LENGTH} characters.`;
  }

  const failed = passwordChecks(password).find((check) => !check.passed);

  return failed ? `Password needs: ${failed.label.toLowerCase()}.` : "";
}

export function fullNameError(name) {
  const cleaned = name.trim().replace(/\s+/g, " ");

  if (cleaned.length < 2) {
    return "Full name must contain at least 2 characters.";
  }

  if (cleaned.length > FULL_NAME_MAX_LENGTH) {
    return `Full name must not exceed ${FULL_NAME_MAX_LENGTH} characters.`;
  }

  return "";
}
