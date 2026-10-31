export function formatVersion(versionNumber) {
  return versionNumber === null || versionNumber === undefined
    ? "—"
    : `V${versionNumber}`;
}

export function formatDate(value) {
  if (!value) return "—";

  return new Date(value).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatTime(value) {
  if (!value) return "";

  return new Date(value).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export function formatFileSize(bytes) {
  if (bytes === null || bytes === undefined) return "";

  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
