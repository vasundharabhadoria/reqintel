from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_SOURCE_COLUMNS = (
    "id, project_id, source_type, original_filename, storage_path, "
    "file_size_bytes, mime_type, raw_text, processing_status, "
    "extraction_error, uploaded_by, uploaded_at"
)


_REQUIREMENT_COLUMNS = (
    "id, project_id, source_id, requirement_code, title, status, "
    "created_by, created_at, updated_at"
)


_VERSION_COLUMNS = (
    "id, requirement_id, version_number, requirement_text, "
    "change_summary, final_quality_score, created_by, created_at"
)


class RequirementRepository:
    """Data access for requirement_sources / requirements /
    requirement_versions. Every query filters by project_id explicitly."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------
    # Sources
    # ---------------------------------------------------------------

    async def create_source(
        self,
        project_id: UUID,
        source_type: str,
        uploaded_by: UUID,
        original_filename: str | None,
        storage_path: str | None,
        file_size_bytes: int | None,
        mime_type: str | None,
        raw_text: str | None,
        processing_status: str,
    ) -> dict:
        result = await self.db.execute(
            text(
                f"""
                INSERT INTO requirement_sources
                    (project_id, source_type, original_filename, storage_path,
                     file_size_bytes, mime_type, raw_text, processing_status,
                     uploaded_by)
                VALUES
                    (:project_id, :source_type, :original_filename, :storage_path,
                     :file_size_bytes, :mime_type, :raw_text, :processing_status,
                     :uploaded_by)
                RETURNING {_SOURCE_COLUMNS}
                """
            ),
            {
                "project_id": project_id,
                "source_type": source_type,
                "original_filename": original_filename,
                "storage_path": storage_path,
                "file_size_bytes": file_size_bytes,
                "mime_type": mime_type,
                "raw_text": raw_text,
                "processing_status": processing_status,
                "uploaded_by": uploaded_by,
            },
        )
        return dict(result.mappings().one())

    async def list_sources(self, project_id: UUID) -> list[dict]:
        result = await self.db.execute(
            text(
                f"""
                SELECT {_SOURCE_COLUMNS}
                FROM requirement_sources
                WHERE project_id = :project_id
                ORDER BY uploaded_at DESC
                """
            ),
            {"project_id": project_id},
        )

        return [dict(row) for row in result.mappings().all()]

    async def get_source(
        self,
        source_id: UUID,
        project_id: UUID,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                SELECT {_SOURCE_COLUMNS}
                FROM requirement_sources
                WHERE id = :source_id AND project_id = :project_id
                """
            ),
            {
                "source_id": source_id,
                "project_id": project_id,
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None

    async def update_source_processing(
        self,
        source_id: UUID,
        project_id: UUID,
        processing_status: str,
        raw_text: str | None = None,
        extraction_error: str | None = None,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                UPDATE requirement_sources
                SET processing_status = :processing_status,
                    raw_text = COALESCE(:raw_text, raw_text),
                    extraction_error = :extraction_error
                WHERE id = :source_id AND project_id = :project_id
                RETURNING {_SOURCE_COLUMNS}
                """
            ),
            {
                "source_id": source_id,
                "project_id": project_id,
                "processing_status": processing_status,
                "raw_text": raw_text,
                "extraction_error": extraction_error,
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None

    # ---------------------------------------------------------------
    # Requirement code generation (concurrency-safe)
    # ---------------------------------------------------------------

    async def lock_project_for_code_generation(
        self,
        project_id: UUID,
    ) -> None:
        """
        Serialize requirement_code generation for this project within the
        current transaction. pg_advisory_xact_lock automatically releases
        at COMMIT/ROLLBACK, so no explicit unlock is needed. Salt 0
        distinguishes this lock namespace from the version-number lock
        below, which is salted 1.
        """

        await self.db.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
            ),
            {"key": str(project_id)},
        )

    async def next_requirement_code(
        self,
        project_id: UUID,
    ) -> str:
        """
        Compute the next REQ-### code for a project. Must be called after
        lock_project_for_code_generation() within the same transaction to
        be safe under concurrent requests.
        """

        result = await self.db.execute(
            text(
                """
                SELECT COALESCE(
                    MAX(
                        CAST(
                            SUBSTRING(
                                requirement_code FROM 'REQ-(\\d+)$'
                            ) AS INTEGER
                        )
                    ),
                    0
                ) AS max_number
                FROM requirements
                WHERE project_id = :project_id
                  AND requirement_code ~ '^REQ-\\d+$'
                """
            ),
            {"project_id": project_id},
        )

        max_number = result.scalar_one()

        return f"REQ-{max_number + 1:03d}"

    async def create_requirement(
        self,
        project_id: UUID,
        source_id: UUID,
        requirement_code: str,
        title: str | None,
        created_by: UUID,
    ) -> dict:
        result = await self.db.execute(
            text(
                f"""
                INSERT INTO requirements
                    (project_id, source_id, requirement_code, title, created_by)
                VALUES
                    (:project_id, :source_id, :requirement_code, :title, :created_by)
                RETURNING {_REQUIREMENT_COLUMNS}
                """
            ),
            {
                "project_id": project_id,
                "source_id": source_id,
                "requirement_code": requirement_code,
                "title": title,
                "created_by": created_by,
            },
        )

        return dict(result.mappings().one())

    async def list_requirements(
        self,
        project_id: UUID,
        status_filter: str | None,
        search: str | None,
        source_id: UUID | None,
    ) -> list[dict]:

        query = f"""
        SELECT r.{_REQUIREMENT_COLUMNS.replace(', ', ', r.')},
               v.version_id AS current_version_id,
               v.version_number AS current_version_number,
               v.requirement_text AS current_requirement_text
        FROM requirements r
        LEFT JOIN v_requirement_current_version v
            ON v.requirement_id = r.id
        WHERE r.project_id = :project_id
        """

        params: dict = {
            "project_id": project_id
        }

        if status_filter and status_filter.lower() != "all":
            query += " AND r.status = :status"
            params["status"] = status_filter

        if source_id:
            query += " AND r.source_id = :source_id"
            params["source_id"] = source_id

        if search:
            query += (
                " AND (r.requirement_code ILIKE :search "
                "OR r.title ILIKE :search "
                "OR v.requirement_text ILIKE :search)"
            )
            params["search"] = f"%{search}%"

        query += " ORDER BY r.requirement_code ASC"

        result = await self.db.execute(
            text(query),
            params,
        )

        return [
            dict(row)
            for row in result.mappings().all()
        ]

    async def get_requirement(
        self,
        requirement_id: UUID,
        project_id: UUID,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                SELECT r.{_REQUIREMENT_COLUMNS.replace(', ', ', r.')},
                       v.version_number AS current_version_number,
                       v.requirement_text AS current_requirement_text
                FROM requirements r
                LEFT JOIN v_requirement_current_version v
                    ON v.requirement_id = r.id
                WHERE r.id = :requirement_id
                  AND r.project_id = :project_id
                """
            ),
            {
                "requirement_id": requirement_id,
                "project_id": project_id,
            },
        )

        row = result.mappings().first()

        return dict(row) if row else None

    # ---------------------------------------------------------------
    # Versions (append-only)
    # ---------------------------------------------------------------

    async def lock_requirement_for_versioning(
        self,
        requirement_id: UUID,
    ) -> None:
        """Serialize version_number generation for one requirement."""

        await self.db.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 1))"
            ),
            {"key": str(requirement_id)},
        )

    async def next_version_number(
        self,
        requirement_id: UUID,
    ) -> int:
        result = await self.db.execute(
            text(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1
                FROM requirement_versions
                WHERE requirement_id = :requirement_id
                """
            ),
            {
                "requirement_id": requirement_id
            },
        )

        return result.scalar_one()

    async def create_version(
        self,
        requirement_id: UUID,
        version_number: int,
        requirement_text: str,
        change_summary: str | None,
        created_by: UUID,
        final_quality_score: float | None = None,
    ) -> dict:
        result = await self.db.execute(
            text(
                f"""
                INSERT INTO requirement_versions
                    (requirement_id, version_number, requirement_text,
                     change_summary, final_quality_score, created_by)
                VALUES
                    (:requirement_id, :version_number, :requirement_text,
                     :change_summary, :final_quality_score, :created_by)
                RETURNING {_VERSION_COLUMNS}
                """
            ),
            {
                "requirement_id": requirement_id,
                "version_number": version_number,
                "requirement_text": requirement_text,
                "change_summary": change_summary,
                "final_quality_score": final_quality_score,
                "created_by": created_by,
            },
        )

        return dict(result.mappings().one())

    async def list_versions(
        self,
        requirement_id: UUID,
    ) -> list[dict]:
        result = await self.db.execute(
            text(
                f"""
                SELECT {_VERSION_COLUMNS}
                FROM requirement_versions
                WHERE requirement_id = :requirement_id
                ORDER BY version_number ASC
                """
            ),
            {
                "requirement_id": requirement_id
            },
        )

        return [
            dict(row)
            for row in result.mappings().all()
        ]

    # ---------------------------------------------------------------
    # Rule validation
    # ---------------------------------------------------------------

    async def create_rule_validation(
        self,
        requirement_version_id: UUID,
        rule_name: str,
        passed: bool,
        message: str,
        severity: str | None = None,
    ) -> dict:
        result = await self.db.execute(
            text(
                """
                INSERT INTO rule_validation
                (
                    requirement_version_id,
                    rule_name,
                    passed,
                    message,
                    severity
                )
                VALUES
                (
                    :requirement_version_id,
                    :rule_name,
                    :passed,
                    :message,
                    :severity
                )
                RETURNING
                    id,
                    requirement_version_id,
                    rule_name,
                    passed,
                    message,
                    severity,
                    evaluated_at
                """
            ),
            {
                "requirement_version_id": requirement_version_id,
                "rule_name": rule_name,
                "passed": passed,
                "message": message,
                "severity": severity,
            },
        )

        return dict(result.mappings().one())
    async def delete_source_cascade(
        self,
        project_id: UUID,
        source_id: UUID,
    ) -> None:
        """
        Permanently delete a source and everything extracted from it.

        Delete order:
        rule_validation -> requirement_versions -> requirements -> source
        This order avoids foreign-key dependency problems.
        """
        await self.db.execute(
            text(
                """
                DELETE FROM rule_validation
                WHERE requirement_version_id IN (
                    SELECT rv.id
                    FROM requirement_versions rv
                    INNER JOIN requirements r
                        ON r.id = rv.requirement_id
                    WHERE r.project_id = :project_id
                      AND r.source_id = :source_id
                )
                """
            ),
            {
                "project_id": project_id,
                "source_id": source_id,
            },
        )

        await self.db.execute(
            text(
                """
                DELETE FROM requirement_versions
                WHERE requirement_id IN (
                    SELECT id
                    FROM requirements
                    WHERE project_id = :project_id
                      AND source_id = :source_id
                )
                """
            ),
            {
                "project_id": project_id,
                "source_id": source_id,
            },
        )

        await self.db.execute(
            text(
                """
                DELETE FROM requirements
                WHERE project_id = :project_id
                  AND source_id = :source_id
                """
            ),
            {
                "project_id": project_id,
                "source_id": source_id,
            },
        )

        await self.db.execute(
            text(
                """
                DELETE FROM requirement_sources
                WHERE project_id = :project_id
                  AND id = :source_id
                """
            ),
            {
                "project_id": project_id,
                "source_id": source_id,
            },
        )
