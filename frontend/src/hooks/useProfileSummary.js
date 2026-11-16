import { useEffect, useSyncExternalStore } from "react";

import { getProfile } from "../api/profileApi";

// The auth session (/auth/me) carries id, email and role but not the full
// name. The shell needs the real name, so it is fetched once from the existing
// profile endpoint and shared by every page instead of being refetched on each
// route change. ProfilePage pushes edits in through `setProfileSummary`.

let summary = null;
let inFlight = null;
const listeners = new Set();

function emit() {
  listeners.forEach((listener) => listener());
}

export function setProfileSummary(next) {
  summary = next;
  emit();
}

export function clearProfileSummary() {
  summary = null;
  inFlight = null;
  emit();
}

// One shared request: if the shell and a page both ask while it is running,
// they get the same promise instead of hitting the API twice. Rejects on error.
export function fetchProfileSummary() {
  if (!inFlight) {
    inFlight = getProfile()
      .then((profile) => {
        summary = profile;
        return profile;
      })
      .finally(() => {
        inFlight = null;
        emit();
      });
  }

  return inFlight;
}

function load() {
  if (summary || inFlight) return;

  // The shell degrades to the e-mail address; pages report their own errors.
  fetchProfileSummary().catch(() => {});
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useProfileSummary(userId) {
  const profile = useSyncExternalStore(subscribe, () => summary);

  // A different account signed in on this tab: drop the previous person's name.
  const stale = profile && userId && profile.id !== userId;

  useEffect(() => {
    if (!userId) return;
    if (stale) clearProfileSummary();
    load();
  }, [userId, stale]);

  return stale ? null : profile;
}
