"""
Supabase Storage helpers for permanent project deletion.

Storage operations cannot join a PostgreSQL transaction, so they are kept
in their own module and only ever run AFTER the database transaction has
committed (or, for listing, BEFORE any deletion starts, read-only).

Safety rules enforced here:
  * only the two known private buckets are ever touched;
  * only objects whose path starts with "<project_id>/" are ever removed,
    so one project's cleanup can never delete another project's files;
  * paths containing ".." or empty segments are rejected;
  * no bucket-level delete is ever issued.
"""

import asyncio
from typing import Any
from uuid import UUID

from core.storage import REPORTS_BUCKET, REQUIREMENT_SOURCES_BUCKET

ALLOWED_BUCKETS = frozenset({REQUIREMENT_SOURCES_BUCKET, REPORTS_BUCKET})

_REMOVE_CHUNK = 100
_LIST_PAGE = 100
_MAX_LIST_DEPTH = 3


def is_safe_object(project_id: UUID | str, bucket: str, path: str) -> bool:
    """True only for a path inside this project's own folder of a known bucket."""

    if bucket not in ALLOWED_BUCKETS or not path:
        return False

    segments = path.split("/")

    if segments[0] != str(project_id) or len(segments) < 2:
        return False

    return all(seg not in ("", ".", "..") for seg in segments)


def _list_folder_sync(client: Any, bucket: str, folder: str, depth: int) -> list[str]:
    found: list[str] = []
    offset = 0

    while True:
        items = (
            client.storage.from_(bucket).list(
                folder, {"limit": _LIST_PAGE, "offset": offset}
            )
            or []
        )

        for item in items:
            name = item.get("name")

            if not name:
                continue

            full = f"{folder}/{name}"

            # Folders come back without an id; files have one.
            if item.get("id") is None:
                if depth < _MAX_LIST_DEPTH:
                    found.extend(_list_folder_sync(client, bucket, full, depth + 1))
            else:
                found.append(full)

        if len(items) < _LIST_PAGE:
            break

        offset += _LIST_PAGE

    return found


async def list_project_objects(
    client: Any, bucket: str, project_id: UUID
) -> list[str]:
    """
    Every object under "<project_id>/" in a bucket. Used to catch files that
    exist in storage but are not referenced by any database row (e.g. an
    upload whose DB update never committed).
    """

    return await asyncio.to_thread(
        _list_folder_sync, client, bucket, str(project_id), 0
    )


def _remove_sync(client: Any, bucket: str, paths: list[str]) -> list[str]:
    """Remove paths; return the paths that could NOT be removed."""

    failed: list[str] = []

    for start in range(0, len(paths), _REMOVE_CHUNK):
        chunk = paths[start : start + _REMOVE_CHUNK]

        try:
            client.storage.from_(bucket).remove(chunk)
        except Exception:
            failed.extend(chunk)

    return failed


async def remove_objects(
    client: Any, objects: list[dict[str, str]]
) -> list[dict[str, str]]:
    """
    Remove {"bucket", "path"} objects. Removing an object that no longer
    exists is not an error, so this is safe to call repeatedly (retry).
    Returns the objects that failed.
    """

    by_bucket: dict[str, list[str]] = {}

    for obj in objects:
        by_bucket.setdefault(obj["bucket"], []).append(obj["path"])

    failed: list[dict[str, str]] = []

    for bucket, paths in by_bucket.items():
        failed_paths = await asyncio.to_thread(_remove_sync, client, bucket, paths)
        failed.extend({"bucket": bucket, "path": p} for p in failed_paths)

    return failed
