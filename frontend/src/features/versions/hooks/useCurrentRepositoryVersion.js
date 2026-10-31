import { useEffect, useState } from "react";

import { listRepositoryVersions } from "../../../api/versionsApi";

/**
 * Current repository version number, read from the repository_versions
 * table (Supabase). Falls back to `fallback` (the number computed from
 * the requirements) until a version exists or if the request fails.
 *
 * `refreshKey` re-reads the value whenever it changes, e.g. after an
 * analysis reloads the requirements.
 */
export function useCurrentRepositoryVersion(
  projectId,
  fallback = null,
  refreshKey = null
) {
  const [stored, setStored] = useState(null);

  useEffect(() => {
    if (!projectId) return undefined;

    let cancelled = false;

    listRepositoryVersions(projectId, { page: 1, pageSize: 1 })
      .then((response) => {
        if (cancelled) return;

        const current = Number(response?.summary?.current_version);
        setStored(Number.isFinite(current) && current > 0 ? current : null);
      })
      .catch(() => {
        if (!cancelled) setStored(null);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, refreshKey]);

  return stored ?? fallback;
}
