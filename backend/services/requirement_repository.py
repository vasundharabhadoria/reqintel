import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.repository_version_repository import (
    RepositoryVersionRepository,
)


_SOURCE_COLUMNS = (
    "id, project_id, source_type, original_filename, storage_path, "
    "file_size_bytes, mime_type, raw_text, processing_status, "
    "extraction_error, uploaded_by, uploaded_at"
)


_REQUIREMENT_COLUMNS = (
    "id, project_id, source_id, requirement_code, title, status, "
    "draft_requirement_text, created_by, created_at, updated_at"
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

    async def list_traceability_links(
        self,
        requirement_id: UUID,
    ) -> list[dict]:
        result = await self.db.execute(
            text("""
                SELECT *
                FROM public.requirement_traceability
                WHERE source_requirement_id = :requirement_id
                   OR target_requirement_id = :requirement_id
                ORDER BY mapped_at DESC
            """),
            {"requirement_id": requirement_id},
        )

        return [dict(row) for row in result.mappings().all()]

    async def create_traceability_link(
        self,
        source_requirement_id: UUID,
        target_requirement_id: UUID,
        link_type: str,
        mapped_by: UUID,
    ) -> dict:
        existing = await self.db.execute(
            text("""
                SELECT *
                FROM public.requirement_traceability
                WHERE source_requirement_id = :source_id
                  AND target_requirement_id = :target_id
                  AND link_type = :link_type
                LIMIT 1
            """),
            {
                "source_id": source_requirement_id,
                "target_id": target_requirement_id,
                "link_type": link_type,
            },
        )

        existing_row = existing.mappings().first()

        if existing_row:
            raise ValueError(
                "This traceability link already exists."
            )

        result = await self.db.execute(
            text("""
                INSERT INTO public.requirement_traceability (
                    source_requirement_id,
                    target_requirement_id,
                    link_type,
                    mapped_by
                )
                VALUES (
                    :source_id,
                    :target_id,
                    :link_type,
                    :mapped_by
                )
                RETURNING *
            """),
            {
                "source_id": source_requirement_id,
                "target_id": target_requirement_id,
                "link_type": link_type,
                "mapped_by": mapped_by,
            },
        )

        return dict(result.mappings().one())

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
                     v.version_id AS current_version_id,
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

    async def update_draft_requirement_text(
        self,
        requirement_id: UUID,
        project_id: UUID,
        draft_requirement_text: str | None,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                f"""
                UPDATE requirements
                SET draft_requirement_text = :draft_requirement_text,
                    updated_at = NOW()
                WHERE id = :requirement_id
                  AND project_id = :project_id
                RETURNING {_REQUIREMENT_COLUMNS}
                """
            ),
            {
                "requirement_id": requirement_id,
                "project_id": project_id,
                "draft_requirement_text": draft_requirement_text,
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None

    async def set_requirement_draft_text(
        self,
        requirement_id: UUID,
        project_id: UUID,
        draft_requirement_text: str | None,
    ) -> dict | None:
        return await self.update_draft_requirement_text(
            requirement_id=requirement_id,
            project_id=project_id,
            draft_requirement_text=draft_requirement_text,
        )

    async def clear_requirement_draft_text(
        self,
        requirement_id: UUID,
        project_id: UUID,
    ) -> dict | None:
        return await self.update_draft_requirement_text(
            requirement_id=requirement_id,
            project_id=project_id,
            draft_requirement_text=None,
        )
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

    async def create_requirements_with_versions_batch(
        self,
        project_id: UUID,
        source_id: UUID,
        requirements: list[dict],
        created_by: UUID,
    ) -> list[dict]:
        """Create requirements and initial versions using two bulk INSERTs."""
        if not requirements:
            return []

        await self.lock_project_for_code_generation(project_id)

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
                )
                FROM requirements
                WHERE project_id = :project_id
                  AND requirement_code ~ '^REQ-\\d+$'
                """
            ),
            {"project_id": project_id},
        )

        start_number = int(result.scalar_one()) + 1

        params = {}
        values = []

        for i, item in enumerate(requirements):
            params[f"id_{i}"] = UUID(str(item["id"]))
            params[f"project_{i}"] = project_id
            params[f"source_{i}"] = source_id
            params[f"code_{i}"] = f"REQ-{start_number + i:03d}"
            params[f"title_{i}"] = item["title"]
            params[f"created_{i}"] = created_by

            values.append(
                f"(:id_{i}, :project_{i}, :source_{i}, :code_{i}, "
                f":title_{i}, :created_{i})"
            )

        result = await self.db.execute(
            text(
                f"""
                INSERT INTO requirements
                    (id, project_id, source_id, requirement_code, title, created_by)
                VALUES {", ".join(values)}
                RETURNING {_REQUIREMENT_COLUMNS}
                """
            ),
            params,
        )

        created = [dict(row) for row in result.mappings().all()]

        version_params = {}
        version_values = []

        for i, item in enumerate(requirements):
            version_params[f"vid_{i}"] = UUID(str(item["version_id"]))
            version_params[f"rid_{i}"] = UUID(str(item["id"]))
            version_params[f"text_{i}"] = item["requirement_text"]
            version_params[f"created_{i}"] = created_by
            version_params[f"summary_{i}"] = "Initial version."

            version_values.append(
                f"(:vid_{i}, :rid_{i}, 1, :text_{i}, "
                f":summary_{i}, NULL, :created_{i})"
            )

        await self.db.execute(
            text(
                f"""
                INSERT INTO requirement_versions
                    (id, requirement_id, version_number, requirement_text,
                     change_summary, final_quality_score, created_by)
                VALUES {", ".join(version_values)}
                """
            ),
            version_params,
        )

        return created

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

    async def list_change_impacts(
        self,
        requirement_version_id: UUID,
    ) -> list[dict]:
        result = await self.db.execute(
            text(
                """
                SELECT
                    id,
                    source_requirement_version_id,
                    affected_requirement_id,
                    affected_module_id,
                    affected_api_id,
                    affected_test_case_id,
                    risk_level,
                    impact_description,
                    ai_generated,
                    created_at
                FROM change_impact_analysis
                WHERE source_requirement_version_id = :version_id
                ORDER BY created_at DESC
                """
            ),
            {"version_id": requirement_version_id},
        )

        return [dict(row) for row in result.mappings().all()]

    async def save_change_impact(
        self,
        source_requirement_version_id: UUID,
        affected_requirement_id: UUID,
        risk_level: str,
        impact_description: str | None = None,
        affected_module_id: UUID | None = None,
        affected_api_id: UUID | None = None,
        affected_test_case_id: UUID | None = None,
        ai_generated: bool = False,
    ) -> dict:
        result = await self.db.execute(
            text(
                """
                INSERT INTO change_impact_analysis (
                    source_requirement_version_id,
                    affected_requirement_id,
                    affected_module_id,
                    affected_api_id,
                    affected_test_case_id,
                    risk_level,
                    impact_description,
                    ai_generated
                )
                VALUES (
                    :source_version_id,
                    :affected_requirement_id,
                    :module_id,
                    :api_id,
                    :test_case_id,
                    CAST(:risk_level AS risk_level_enum),
                    :description,
                    :ai_generated
                )
                RETURNING *
                """
            ),
            {
                "source_version_id": source_requirement_version_id,
                "affected_requirement_id": affected_requirement_id,
                "module_id": affected_module_id,
                "api_id": affected_api_id,
                "test_case_id": affected_test_case_id,
                "risk_level": risk_level,
                "description": impact_description,
                "ai_generated": ai_generated,
            },
        )

        row = result.mappings().one()
        return dict(row)

    async def get_latest_analysis(
        self,
        requirement_id: UUID,
    ) -> dict | None:
        """
        Return the latest repository version and its latest AI analysis.

        This is read-only. It does not run Rule Engine or AI.
        It is used when the Requirements page is refreshed/re-opened.
        """
        result = await self.db.execute(
            text(
                """
                SELECT
                    rv.id AS requirement_version_id,
                    rv.requirement_id,
                    rv.version_number,
                    rv.requirement_text,
                    rv.change_summary,
                    rv.final_quality_score,
                    rv.created_by AS version_created_by,
                    rv.created_at AS version_created_at,
                    aa.id AS ai_analysis_id,
                    aa.model_name,
                    aa.prompt_type,
                    aa.analysis_summary,
                    aa.recommendations,
                    aa.raw_response_json,
                    aa.ambiguity_detected,
                    aa.created_at AS ai_created_at
                FROM requirement_versions rv
                LEFT JOIN LATERAL (
                    SELECT
                        a.id,
                        a.model_name,
                        a.prompt_type,
                        a.analysis_summary,
                        a.recommendations,
                        a.raw_response_json,
                        a.ambiguity_detected,
                        a.created_at
                    FROM ai_analysis a
                    WHERE a.requirement_version_id = rv.id
                    ORDER BY a.created_at DESC
                    LIMIT 1
                ) aa ON TRUE
                WHERE rv.requirement_id = :requirement_id
                ORDER BY rv.version_number DESC
                LIMIT 1
                """
            ),
            {"requirement_id": requirement_id},
        )

        row = result.mappings().first()
        return dict(row) if row else None

    async def list_ai_suggestions(
        self,
        ai_analysis_id: UUID,
    ) -> list[dict]:
        """Return all saved AI suggestions and their current review status."""
        result = await self.db.execute(
            text(
                """
                SELECT
                    id,
                    ai_analysis_id,
                    suggestion_text,
                    suggestion_type,
                    status,
                    resolved_text,
                    reviewed_by,
                    reviewed_at,
                    created_at
                FROM ai_suggestions
                WHERE ai_analysis_id = :ai_analysis_id
                ORDER BY created_at ASC
                """
            ),
            {"ai_analysis_id": ai_analysis_id},
        )

        return [
            dict(row)
            for row in result.mappings().all()
        ]

    async def get_ai_suggestion_for_requirement(
        self,
        requirement_id: UUID,
        suggestion_id: UUID,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                """
                SELECT
                    s.id,
                    s.ai_analysis_id,
                    s.suggestion_text,
                    s.suggestion_type,
                    s.status,
                    s.resolved_text,
                    s.reviewed_by,
                    s.reviewed_at,
                    s.created_at
                FROM ai_suggestions s
                INNER JOIN ai_analysis aa
                    ON aa.id = s.ai_analysis_id
                INNER JOIN requirement_versions rv
                    ON rv.id = aa.requirement_version_id
                WHERE s.id = :suggestion_id
                  AND rv.requirement_id = :requirement_id
                """
            ),
            {
                "suggestion_id": suggestion_id,
                "requirement_id": requirement_id,
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None

    async def update_ai_suggestion_status(
        self,
        suggestion_id: UUID,
        status: str,
        reviewed_by: UUID,
    ) -> dict | None:
        result = await self.db.execute(
            text(
                """
                UPDATE ai_suggestions
                SET
                    status = :status,
                    reviewed_by = :reviewed_by,
                    reviewed_at = NOW()
                WHERE id = :suggestion_id
                RETURNING
                    id,
                    ai_analysis_id,
                    suggestion_text,
                    suggestion_type,
                    status,
                    resolved_text,
                    reviewed_by,
                    reviewed_at,
                    created_at
                """
            ),
            {
                "suggestion_id": suggestion_id,
                "status": status,
                "reviewed_by": reviewed_by,
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None

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

    # ---------------------------------------------------------------
    # AI analysis
    # ---------------------------------------------------------------

    async def create_ai_analysis(
        self,
        requirement_version_id: UUID,
        model_name: str,
        prompt_type: str,
        analysis_summary: str | None,
        recommendations: str | None,
        raw_response_json: dict | None,
        ambiguity_detected: bool,
    ) -> dict:
        result = await self.db.execute(
            text(
                """
                INSERT INTO ai_analysis
                (
                    requirement_version_id,
                    model_name,
                    prompt_type,
                    analysis_summary,
                    recommendations,
                    raw_response_json,
                    ambiguity_detected
                )
                VALUES
                (
                    :requirement_version_id,
                    :model_name,
                    :prompt_type,
                    :analysis_summary,
                    :recommendations,
                    CAST(:raw_response_json AS jsonb),
                    :ambiguity_detected
                )
                RETURNING
                    id,
                    requirement_version_id,
                    model_name,
                    prompt_type,
                    analysis_summary,
                    recommendations,
                    raw_response_json,
                    ambiguity_detected,
                    created_at
                """
            ),
            {
                "requirement_version_id": requirement_version_id,
                "model_name": model_name,
                "prompt_type": prompt_type,
                "analysis_summary": analysis_summary,
                "recommendations": recommendations,
                "raw_response_json": (
                    json.dumps(raw_response_json)
                    if raw_response_json is not None
                    else None
                ),
                "ambiguity_detected": ambiguity_detected,
            },
        )

        return dict(result.mappings().one())

    async def create_ai_suggestion(
        self,
        ai_analysis_id: UUID,
        suggestion_text: str,
        suggestion_type: str,
        resolved_text: str | None = None,
    ) -> dict:
        result = await self.db.execute(
            text(
                """
                INSERT INTO ai_suggestions
                (
                    ai_analysis_id,
                    suggestion_text,
                    suggestion_type,
                    status,
                    resolved_text
                )
                VALUES
                (
                    :ai_analysis_id,
                    :suggestion_text,
                    :suggestion_type,
                    'pending',
                    :resolved_text
                )
                RETURNING
                    id,
                    ai_analysis_id,
                    suggestion_text,
                    suggestion_type,
                    status,
                    resolved_text,
                    reviewed_by,
                    reviewed_at,
                    created_at
                """
            ),
            {
                "ai_analysis_id": ai_analysis_id,
                "suggestion_text": suggestion_text,
                "suggestion_type": suggestion_type,
                "resolved_text": resolved_text,
            },
        )

        return dict(result.mappings().one())

    async def update_requirement_status(
        self,
        requirement_id: UUID,
        project_id: UUID,
        status: str,
    ) -> dict | None:
        """Update only the review status of a requirement.

        Approve/reject does not create a new version and does not run
        Rule Engine or AI analysis.
        """
        result = await self.db.execute(
            text(
                f"""
                UPDATE requirements
                SET
                    status = :status,
                    updated_at = NOW()
                WHERE id = :requirement_id
                  AND project_id = :project_id
                RETURNING {_REQUIREMENT_COLUMNS}
                """
            ),
            {
                "requirement_id": requirement_id,
                "project_id": project_id,
                "status": status,
            },
        )

        row = result.mappings().first()
        return dict(row) if row else None

    async def delete_source_cascade(
        self,
        source_id: UUID,
    ) -> None:
        """
        Delete a source and its dependent records in the correct order.

        Dependent AI suggestions, AI analyses, rule validations,
        requirement versions, and requirements are deleted before
        the source record.
        """
        await self.db.execute(
            text(
                """
                DELETE FROM ai_suggestions
                WHERE ai_analysis_id IN (
                    SELECT aa.id
                    FROM ai_analysis aa
                    INNER JOIN requirement_versions rv
                        ON rv.id = aa.requirement_version_id
                    INNER JOIN requirements r
                        ON r.id = rv.requirement_id
                    WHERE r.source_id = :source_id
                )
                """
            ),
            {"source_id": source_id},
        )

        await self.db.execute(
            text(
                """
                DELETE FROM ai_analysis
                WHERE requirement_version_id IN (
                    SELECT rv.id
                    FROM requirement_versions rv
                    INNER JOIN requirements r
                        ON r.id = rv.requirement_id
                    WHERE r.source_id = :source_id
                )
                """
            ),
            {"source_id": source_id},
        )

        await self.db.execute(
            text(
                """
                DELETE FROM rule_validation
                WHERE requirement_version_id IN (
                    SELECT rv.id
                    FROM requirement_versions rv
                    INNER JOIN requirements r
                        ON r.id = rv.requirement_id
                    WHERE r.source_id = :source_id
                )
                """
            ),
            {"source_id": source_id},
        )

        await self.db.execute(
            text(
                """
                DELETE FROM change_impact_analysis
                WHERE source_requirement_version_id IN (
                        SELECT rv.id
                        FROM requirement_versions rv
                        INNER JOIN requirements r ON r.id = rv.requirement_id
                        WHERE r.source_id = :source_id
                    )
                   OR affected_requirement_id IN (
                        SELECT id FROM requirements WHERE source_id = :source_id
                    )
                """
            ),
            {"source_id": source_id},
        )

        await self.db.execute(
            text(
                """
                DELETE FROM requirement_traceability
                WHERE source_requirement_id IN (
                        SELECT id FROM requirements WHERE source_id = :source_id
                    )
                   OR target_requirement_id IN (
                        SELECT id FROM requirements WHERE source_id = :source_id
                    )
                """
            ),
            {"source_id": source_id},
        )

        await self.db.execute(
            text(
                """
                DELETE FROM requirement_versions
                WHERE requirement_id IN (
                    SELECT id
                    FROM requirements
                    WHERE source_id = :source_id
                )
                """
            ),
            {"source_id": source_id},
        )

        await self.db.execute(
            text(
                """
                DELETE FROM requirements
                WHERE source_id = :source_id
                """
            ),
            {"source_id": source_id},
        )

        await self.db.execute(
            text(
                """
                DELETE FROM requirement_sources
                WHERE id = :source_id
                """
            ),
            {"source_id": source_id},
        )

    async def list_project_traceability_links(
        self,
        project_id: UUID,
    ) -> list[dict]:
        """Return all traceability links belonging to a project."""
        result = await self.db.execute(
            text(
                """
                SELECT
                    rt.*
                FROM public.requirement_traceability rt
                INNER JOIN public.requirements source_req
                    ON source_req.id = rt.source_requirement_id
                INNER JOIN public.requirements target_req
                    ON target_req.id = rt.target_requirement_id
                WHERE source_req.project_id = :project_id
                  AND target_req.project_id = :project_id
                ORDER BY rt.mapped_at DESC
                """
            ),
            {"project_id": project_id},
        )

        return [
            dict(row)
            for row in result.mappings().all()
        ] 

    async def create_repository_version_snapshot(
        self,
        project_id: UUID,
        created_by: UUID,
        change_summary: str | None = None,
    ) -> dict | None:
        """
        Create the next repository version (V1, V2, ...) for a project.

        Returns the new row, or None when nothing changed since the
        latest version. The summary text is generated from the
        comparison; change_summary is kept only for older callers.
        """

        return await RepositoryVersionRepository(self.db).create_snapshot(
            project_id=project_id,
            created_by=created_by,
        )
