export const FULL_NAME_MIN_LENGTH = 2;
export const FULL_NAME_MAX_LENGTH = 150;

export function roleLabel(role) {
  if (!role) return "User";

  return role
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

const PROVIDER_LABELS = {
  email: "Email & password",
  google: "Google",
  github: "GitHub",
};

export function providerLabel(provider) {
  return PROVIDER_LABELS[provider] || provider || "Unknown";
}

export function formatDate(value) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

// Mirrors the backend rules (auth.schemas.normalise_full_name). The server
// stays the source of truth; this only gives instant feedback.
export function validateFullName(value) {
  const name = value.trim().replace(/\s+/g, " ");

  if (name.length < FULL_NAME_MIN_LENGTH) {
    return `Full name must contain at least ${FULL_NAME_MIN_LENGTH} characters.`;
  }

  if (name.length > FULL_NAME_MAX_LENGTH) {
    return `Full name must not exceed ${FULL_NAME_MAX_LENGTH} characters.`;
  }

  return "";
}
