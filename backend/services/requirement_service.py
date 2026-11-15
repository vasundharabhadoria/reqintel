import asyncio
import json
import re
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage import REQUIREMENT_SOURCES_BUCKET, get_storage_client
from core.supabase import get_rules_client
from models.requirement import (
    ExtractedRequirementSummary,
    ManualRequirementCreate,
    RequirementResponse,
    RequirementSourceResponse,
    RequirementVersionCreate,
    RequirementVersionResponse,
)
from services.project_repository import ProjectRepository
from services.requirement_extraction import ExtractionError, extract_text
from services.ai_requirement_extraction import AIRequirementExtractionStrategy
from services.ai_analysis import AIAnalysisService, is_blocking_finding
from services.requirement_repository import RequirementRepository


_ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
}

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
class RequirementService:
    """
    Business logic for Module 2 (Requirements).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.repo = RequirementRepository(db)
        self.storage = get_storage_client()
        self.extraction_strategy = AIRequirementExtractionStrategy()
        self.ai_analysis = AIAnalysisService()
        self._last_snapshot_error: str | None = None

    

    async def create_traceability_link(
        self,
        owner_id: UUID,
        project_id: UUID,
        source_requirement_id: UUID,
        target_requirement_id: UUID,
        link_type: str,
    ) -> dict:
        
        valid_link_types = {
            "depends_on",
            "duplicates",
            "conflicts_with",
            "relates_to",
            "derived_from",
        }

        if link_type not in valid_link_types:
            raise ValueError(
                f"Invalid link_type. Allowed values: {', '.join(sorted(valid_link_types))}"
            )

        await self._require_project(owner_id, project_id)

        await self._require_requirement(
            project_id, source_requirement_id
        )
        await self._require_requirement(
            project_id, target_requirement_id
        )

        if source_requirement_id == target_requirement_id:
            raise ValueError("A requirement cannot be linked to itself.")

        try:
            result = await self.repo.create_traceability_link(
                source_requirement_id=source_requirement_id,
                target_requirement_id=target_requirement_id,
                link_type=link_type,
                mapped_by=owner_id,
            )
            await self.db.commit()
            return result
        except Exception:
            await self.db.rollback()
            raise

    async def list_traceability_links(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
    ) -> list[dict]:
        await self._require_project(owner_id, project_id)
        await self._require_requirement(project_id, requirement_id)

        return await self.repo.list_traceability_links(
            requirement_id=requirement_id
        )

    async def list_project_traceability_links(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> list[dict]:
        await self._require_project(owner_id, project_id)

        return await self.repo.list_project_traceability_links(
            project_id=project_id
        )


    def _load_master_rules_for_ai(self) -> list[dict]:
        """Load active Master Module rules and category context for AI analysis."""
        try:
            rules_response = (
                get_rules_client().from_("master_rules")
                .select(
                    "id, category_id, rule, description, why_it_matters, "
                    "recommendation, rule_type, severity, is_active"
                )
                .eq("is_active", True)
                .execute()
            )

            rules = rules_response.data or []
            if not rules:
                return []

            category_ids = list({
                rule["category_id"]
                for rule in rules
                if rule.get("category_id")
            })

            if not category_ids:
                return rules

            categories_response = (
                get_rules_client().from_("rule_categories")
                .select(
                    "id, name, description, evaluation_mode, is_active"
                )
                .in_("id", category_ids)
                .eq("is_active", True)
                .execute()
            )

            categories = categories_response.data or []
            category_map = {
                category["id"]: category
                for category in categories
            }

            enriched = []
            for rule in rules:
                category = category_map.get(rule.get("category_id"))
                if not category:
                    continue

                enriched.append({
                    **rule,
                    "category_name": category.get("name") or "Other",
                    "category_description": category.get("description") or "",
                    "evaluation_mode": category.get("evaluation_mode") or "Issue",
                })

            print(
                f"[AI ANALYSIS] Loaded {len(enriched)} active master rules."
            )
            return enriched

        except Exception as exc:
            print(
                "[AI ANALYSIS] Master rule load failed:",
                repr(exc),
            )
            return []
    async def suggest_traceability_links(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> list[dict]:
        await self._require_project(owner_id, project_id)

        requirements = await self.repo.list_requirements(
            project_id,
            None,
            None,
            None,
        )

        existing_links = await self.repo.list_project_traceability_links(
            project_id=project_id
        )

        suggestions = await self.ai_analysis.suggest_traceability_links(
            requirements=requirements,
            existing_links=existing_links,
        )

        return suggestions
    async def _create_repository_snapshot(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> dict | None:
        """
        Create the next repository version without ever breaking the
        analysis that triggered it. Runs in a SAVEPOINT: if it fails
        (e.g. the table is not created yet) only the snapshot is rolled
        back and the analysis results are still committed.
        """

        self._last_snapshot_error = None

        try:
            async with self.db.begin_nested():
                return await self.repo.create_repository_version_snapshot(
                    project_id=project_id,
                    created_by=owner_id,
                )
        except Exception as exc:
            import traceback

            print(
                "[REPOSITORY VERSION] Snapshot failed, analysis "
                f"results are kept: {exc}"
            )
            traceback.print_exc()
            self._last_snapshot_error = f"{type(exc).__name__}: {exc}"
            return None

    async def _current_repository_version(
        self,
        project_id: UUID,
    ) -> int | None:
        """Current number in repository_versions (None if none/err)."""

        try:
            async with self.db.begin_nested():
                result = await self.db.execute(
                    text(
                        """
                        SELECT version_number
                        FROM repository_versions
                        WHERE project_id = :project_id
                          AND is_current = TRUE
                        LIMIT 1
                        """
                    ),
                    {"project_id": project_id},
                )
                value = result.scalar_one_or_none()
                return int(value) if value is not None else None
        except Exception as exc:
            print(f"[REPOSITORY VERSION] Could not read current version: {exc}")
            return None

    async def _require_project(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> None:
        project = await self.projects.get_by_id(
            project_id,
            owner_id,
        )

        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

    async def _require_source(
        self,
        project_id: UUID,
        source_id: UUID,
    ) -> dict:
        source = await self.repo.get_source(
            source_id,
            project_id,
        )

        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement source not found.",
            )

        return source

    async def _require_requirement(
        self,
        project_id: UUID,
        requirement_id: UUID,
    ) -> dict:
        requirement = await self.repo.get_requirement(
            requirement_id,
            project_id,
        )

        if requirement is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement not found.",
            )

        return requirement

    # ---------------------------------------------------------------
    # Sources
    # ---------------------------------------------------------------

    async def list_sources(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> list[RequirementSourceResponse]:
        await self._require_project(
            owner_id,
            project_id,
        )

        rows = await self.repo.list_sources(project_id)

        return [
            RequirementSourceResponse.model_validate(row)
            for row in rows
        ]

    async def upload_source(
        self,
        owner_id: UUID,
        project_id: UUID,
        file: UploadFile,
    ) -> RequirementSourceResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file selected.",
            )

        extension = (
            "."
            + file.filename.rsplit(".", 1)[-1].lower()
            if "." in file.filename
            else ""
        )

        source_type = _ALLOWED_EXTENSIONS.get(extension)

        if source_type is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only PDF, DOCX, and TXT files are supported.",
            )

        if (
            file.content_type
            and file.content_type not in _ALLOWED_MIME_TYPES
        ):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="File content type does not match a supported format.",
            )

        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is empty.",
            )

        if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds the 50 MB upload limit.",
            )

        source = await self.repo.create_source(
            project_id=project_id,
            source_type=source_type,
            uploaded_by=owner_id,
            original_filename=file.filename,
            storage_path=None,
            file_size_bytes=len(file_bytes),
            mime_type=file.content_type,
            raw_text=None,
            processing_status="uploaded",
        )

        storage_path = (
            f"{project_id}/{source['id']}{extension}"
        )

        try:
            self.storage.storage.from_(
                REQUIREMENT_SOURCES_BUCKET
            ).upload(
                storage_path,
                file_bytes,
                {
                    "content-type": (
                        file.content_type
                        or "application/octet-stream"
                    )
                },
            )

        except Exception as exc:
            await self.repo.update_source_processing(
                source["id"],
                project_id,
                processing_status="failed",
                extraction_error=f"Storage upload failed: {exc}",
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store the uploaded file.",
            ) from exc

        updated = await self.repo.update_source_processing(
            source["id"],
            project_id,
            processing_status="uploaded",
        )

        await self.db.execute(
            text(
                """
                UPDATE requirement_sources
                SET storage_path = :storage_path
                WHERE id = :source_id
                """
            ),
            {
                "storage_path": storage_path,
                "source_id": source["id"],
            },
        )

        updated["storage_path"] = storage_path

        await self.db.commit()

        return RequirementSourceResponse.model_validate(
            updated
        )

    async def get_source_file(
        self,
        owner_id: UUID,
        project_id: UUID,
        source_id: UUID,
    ):
        await self._require_project(
            owner_id,
            project_id,
        )

        source = await self._require_source(
            project_id,
            source_id,
        )

        if not source.get("storage_path"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found.",
            )

        try:
            file_bytes = self.storage.storage.from_(
                REQUIREMENT_SOURCES_BUCKET
            ).download(
                source["storage_path"]
            )

        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve the stored file.",
            ) from exc

        from fastapi.responses import Response

        return Response(
            content=file_bytes,
            media_type=source.get("mime_type")
            or "application/octet-stream",
            headers={
                "Content-Disposition": (
                    f'inline; filename="{source["original_filename"]}"'
                )
            },
        )

    async def extract_source_text(
        self,
        owner_id: UUID,
        project_id: UUID,
        source_id: UUID,
    ) -> RequirementSourceResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        source = await self._require_source(
            project_id,
            source_id,
        )

        if source["source_type"] == "manual":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manual sources do not require extraction.",
            )

        if not source["storage_path"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This source has no stored file to extract from.",
            )

        await self.repo.update_source_processing(
            source_id,
            project_id,
            processing_status="parsing",
        )

        try:
            file_bytes = self.storage.storage.from_(
                REQUIREMENT_SOURCES_BUCKET
            ).download(
                source["storage_path"]
            )

        except Exception as exc:
            await self.repo.update_source_processing(
                source_id,
                project_id,
                processing_status="failed",
                extraction_error=(
                    f"Could not download stored file: {exc}"
                ),
            )
            await self.db.commit()

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve the stored file.",
            ) from exc

        try:
            extracted_text = extract_text(
                file_bytes,
                source["source_type"],
            )

        except ExtractionError as exc:
            await self.repo.update_source_processing(
                source_id,
                project_id,
                processing_status="failed",
                extraction_error=str(exc),
            )
            await self.db.commit()

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        if not extracted_text:
            await self.repo.update_source_processing(
                source_id,
                project_id,
                processing_status="failed",
                extraction_error=(
                    "No text could be extracted from the document."
                ),
            )
            await self.db.commit()

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No text could be extracted from the document.",
            )

        updated = await self.repo.update_source_processing(
            source_id,
            project_id,
            processing_status="completed",
            raw_text=extracted_text,
        )
        await self.db.commit()

        return RequirementSourceResponse.model_validate(
            updated
        )

    # ---------------------------------------------------------------
    # Manual requirement
    # ---------------------------------------------------------------

    async def create_manual_requirement(
        self,
        owner_id: UUID,
        project_id: UUID,
        payload: ManualRequirementCreate,
    ) -> RequirementResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        source = await self.repo.create_source(
            project_id=project_id,
            source_type="manual",
            uploaded_by=owner_id,
            original_filename=None,
            storage_path=None,
            file_size_bytes=None,
            mime_type=None,
            raw_text=payload.requirement_text,
            processing_status="completed",
        )

        requirement, _version = (
            await self._create_requirement_with_version(
                project_id=project_id,
                source_id=source["id"],
                title=payload.title,
                requirement_text=payload.requirement_text,
                created_by=owner_id,
            )
        )

        await self.db.commit()

        return await self.get_requirement(
            owner_id,
            project_id,
            requirement["id"],
        )

    # ---------------------------------------------------------------
    # Requirement identification
    # ---------------------------------------------------------------

    async def extract_requirements(
        self,
        owner_id: UUID,
        project_id: UUID,
        source_id: UUID,
    ) -> ExtractedRequirementSummary:

        await self._require_project(
            owner_id,
            project_id,
        )

        source = await self._require_source(
            project_id,
            source_id,
        )

        if not source["raw_text"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This source has no extracted text yet. "
                    "Run text extraction first."
                ),
            )

        extraction_result = (
            self.extraction_strategy.identify_structured(
                source["raw_text"]
            )
        )
        print(
            f"[DB SAVE] Starting save of "
            f"{len(extraction_result.requirements)} requirements"
        )

        candidate_statements = [
            requirement.text
            for requirement in extraction_result.requirements
        ]

        print(
            f"[DB SAVE] Batch saving {len(candidate_statements)} requirements"
        )

        batch_rows = [
            {
                "id": uuid4(),
                "version_id": uuid4(),
                "title": (
                    statement[:80]
                    + ("…" if len(statement) > 80 else "")
                ),
                "requirement_text": statement,
            }
            for statement in candidate_statements
        ]

        created_rows = await self.repo.create_requirements_with_versions_batch(
            project_id=project_id,
            source_id=source_id,
            requirements=batch_rows,
            created_by=owner_id,
        )

        created_ids = {row["id"] for row in created_rows}

        current_rows = await self.repo.list_requirements(
            project_id,
            None,
            None,
            source_id,
        )

        created = [
            RequirementResponse.model_validate(row)
            for row in current_rows
            if row["id"] in created_ids
        ]

        # Persist: get_db() rolls back anything left uncommitted.
        await self.db.commit()

        print(
            f"[DB SAVE] Batch save complete: {len(created)} requirements"
        )

        return ExtractedRequirementSummary(
            requirements_created=len(created),
            items=created,
            is_srs=extraction_result.is_srs,
   )

    async def _create_requirement_with_version(
        self,
        project_id: UUID,
        source_id: UUID,
        title: str | None,
        requirement_text: str,
        created_by: UUID,
    ) -> tuple[dict, dict]:

        await self.repo.lock_project_for_code_generation(
            project_id
        )

        code = await self.repo.next_requirement_code(
            project_id
        )

        requirement = await self.repo.create_requirement(
            project_id=project_id,
            source_id=source_id,
            requirement_code=code,
            title=title,
            created_by=created_by,
        )

        version = await self.repo.create_version(
            requirement_id=requirement["id"],
            version_number=1,
            requirement_text=requirement_text,
            change_summary="Initial version.",
            created_by=created_by,
        )

        return requirement, version

    # ---------------------------------------------------------------
    # Requirements read/search/filter
    # ---------------------------------------------------------------

    async def list_requirements(
        self,
        owner_id: UUID,
        project_id: UUID,
        status_filter: str | None,
        search: str | None,
        source_id: UUID | None,
    ) -> list[RequirementResponse]:

        await self._require_project(
            owner_id,
            project_id,
        )

        rows = await self.repo.list_requirements(
            project_id,
            status_filter,
            search,
            source_id,
        )

        return [
            RequirementResponse.model_validate(row)
            for row in rows
        ]

    async def get_requirement(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
    ) -> RequirementResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        row = await self._require_requirement(
            project_id,
            requirement_id,
        )

        return RequirementResponse.model_validate(row)

    # ---------------------------------------------------------------
    # RULE ENGINE
    # ---------------------------------------------------------------

    async def get_saved_project_analysis(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> dict:
        """
        Load the latest saved Rule Engine + AI analysis for the project.

        This is a read-only path. It never runs the Rule Engine,
        calls the AI provider, deletes validation rows, or creates
        new analysis records.
        """
        await self._require_project(
            owner_id,
            project_id,
        )

        requirements = await self.repo.list_requirements(
            project_id,
            None,
            None,
            None,
        )

        if not requirements:
            return {
                "total": 0,
                "saved": 0,
                "ai_analyzed": 0,
                "results": [],
                "ai_results": [],
                "cached": True,
                "analysis_available": False,
                "has_unanalyzed_changes": False,
                "repository_version": await self._current_repository_version(
                    project_id
                ),
            }

        draft_result = await self.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM requirements
                WHERE project_id = :project_id
                  AND draft_requirement_text IS NOT NULL
                  AND BTRIM(draft_requirement_text) <> ''
                """
            ),
            {"project_id": project_id},
        )

        has_unanalyzed_changes = int(draft_result.scalar_one() or 0) > 0

        current_versions_result = await self.db.execute(
            text(
                """
                SELECT
                    r.id AS requirement_id,
                    v.id AS requirement_version_id,
                    v.version_number
                FROM requirements r
                INNER JOIN LATERAL (
                    SELECT
                        id,
                        version_number
                    FROM requirement_versions rv
                    WHERE rv.requirement_id = r.id
                    ORDER BY version_number DESC
                    LIMIT 1
                ) v ON TRUE
                WHERE r.project_id = :project_id
                ORDER BY r.requirement_code ASC
                """
            ),
            {
                "project_id": project_id,
            },
        )

        current_versions = [
            dict(row)
            for row in current_versions_result.mappings().all()
        ]

        if not current_versions:
            return {
                "total": 0,
                "saved": 0,
                "ai_analyzed": 0,
                "results": [],
                "ai_results": [],
                "cached": True,
                "analysis_available": False,
                "repository_version": await self._current_repository_version(
                    project_id
                ),
            }

        cached_analysis_result = await self.db.execute(
            text(
                """
                SELECT DISTINCT rv.requirement_id
                FROM requirement_versions rv
                INNER JOIN ai_analysis aa
                    ON aa.requirement_version_id = rv.id
                INNER JOIN requirements r
                    ON r.id = rv.requirement_id
                WHERE r.project_id = :project_id
                  AND rv.version_number = (
                      SELECT MAX(rv2.version_number)
                      FROM requirement_versions rv2
                      WHERE rv2.requirement_id = rv.requirement_id
                  )
                  AND COALESCE(
                      jsonb_array_length(
                          COALESCE(
                              aa.raw_response_json -> 'suggestions',
                              '[]'::jsonb
                          )
                      ),
                      0
                  ) = (
                      SELECT COUNT(*)
                      FROM ai_suggestions ais
                      WHERE ais.ai_analysis_id = aa.id
                  )
                """
            ),
            {
                "project_id": project_id,
            },
        )

        analyzed_requirement_ids = {
            UUID(str(row["requirement_id"]))
            for row in cached_analysis_result.mappings().all()
        }

        current_requirement_ids = {
            UUID(str(row["requirement_id"]))
            for row in current_versions
        }

        if current_requirement_ids != analyzed_requirement_ids:
            requires_ai_analysis = any(
                int(item.get("version_number") or 0) > 1
                for item in current_versions
                if UUID(str(item["requirement_id"]))
                not in analyzed_requirement_ids
            )

            return {
                "total": len(current_versions),
                "saved": 0,
                "ai_analyzed": 0,
                "results": [],
                "ai_results": [],
                "cached": False,
                "analysis_available": False,
                "has_unanalyzed_changes": has_unanalyzed_changes,
                "requires_ai_analysis": requires_ai_analysis,
                "repository_version": await self._current_repository_version(
                    project_id
                ),
            }

        cached_results = []
        cached_ai_results = []
        cached_saved_count = 0

        waivers_by_version = await self._load_waivers(
            [
                UUID(str(item["requirement_version_id"]))
                for item in current_versions
            ]
        )

        for current in current_versions:
            requirement_id = UUID(
                str(current["requirement_id"])
            )
            requirement_version_id = UUID(
                str(current["requirement_version_id"])
            )

            validation_result = await self.db.execute(
                text(
                    """
                    SELECT
                        id,
                        requirement_version_id,
                        rule_name,
                        passed,
                        message,
                        severity,
                        evaluated_at
                    FROM rule_validation
                    WHERE requirement_version_id = :requirement_version_id
                    ORDER BY evaluated_at ASC, rule_name ASC
                    """
                ),
                {
                    "requirement_version_id":
                        requirement_version_id,
                },
            )

            findings = [
                {
                    "id": str(row["id"]),
                    "rule_name": row["rule_name"],
                    "passed": bool(row["passed"]),
                    "message": row["message"],
                    "severity": row["severity"],
                    "evaluated_at": row["evaluated_at"],
                }
                for row in validation_result.mappings().all()
            ]

            # A waived issue is shown as handled (passed + waived flag).
            # The stored rule_validation row is not changed.
            version_waivers = waivers_by_version.get(
                str(requirement_version_id),
                {},
            )

            for finding in findings:
                waiver = version_waivers.get(
                    str(finding["rule_name"]).strip().lower()
                )

                if waiver is not None and not finding["passed"]:
                    finding["passed"] = True
                    finding["waived"] = True
                    finding["waived_reason"] = waiver

            cached_saved_count += len(findings)

            cached_results.append(
                {
                    "id": str(requirement_id),
                    "findings": findings,
                    "cached": True,
                }
            )

            ai_result = await self.db.execute(
                text(
                    """
                    SELECT
                        id,
                        requirement_version_id,
                        model_name,
                        prompt_type,
                        analysis_summary,
                        recommendations,
                        raw_response_json,
                        ambiguity_detected,
                        created_at
                    FROM ai_analysis aa                    WHERE requirement_version_id =
                        :requirement_version_id
                      AND COALESCE(
                          jsonb_array_length(
                              COALESCE(
                                  aa.raw_response_json -> 'suggestions',
                                  '[]'::jsonb
                              )
                          ),
                          0
                      ) = (
                          SELECT COUNT(*)
                          FROM ai_suggestions ais
                          WHERE ais.ai_analysis_id = aa.id
                      )                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "requirement_version_id":
                        requirement_version_id,
                },
            )

            cached_analysis = ai_result.mappings().first()

            if cached_analysis:
                suggestion_result = await self.db.execute(
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
                        WHERE ai_analysis_id =
                            :ai_analysis_id
                        ORDER BY created_at ASC
                        """
                    ),
                    {
                        "ai_analysis_id":
                            cached_analysis["id"],
                    },
                )

                cached_suggestions = [
                    dict(row)
                    for row in suggestion_result.mappings().all()
                ]

                cached_ai_results.append(
                    {
                        "requirement_id":
                            str(requirement_id),
                        "analysis":
                            dict(cached_analysis),
                        "suggestions":
                            cached_suggestions,
                        "cached": True,
                    }
                )

        # A newly-created V2+ version has no AI analysis yet, so the
        # Rule Engine Analyze button must become enabled. V1 is not
        # treated as pending here because the first Requirements-page
        # Analyze action already performs its full analysis.
        analyzed_current_ids = {
            UUID(str(item["requirement_id"]))
            for item in current_versions
            if any(
                str(ai_item.get("requirement_id"))
                == str(item["requirement_id"])
                for ai_item in cached_ai_results
            )
        }

        requires_ai_analysis = any(
            int(item.get("version_number") or 0) > 1
            and UUID(str(item["requirement_id"]))
            not in analyzed_current_ids
            for item in current_versions
        )

        print(
            f"[ANALYSIS] Loaded saved Rule Engine + AI "
            f"results for project {project_id}."
        )

        return {
            "total": len(current_versions),
            "saved": cached_saved_count,
            "ai_analyzed": len(cached_ai_results),
            "results": cached_results,
            "ai_results": cached_ai_results,
            "cached": True,
            "analysis_available": not requires_ai_analysis,
            "has_unanalyzed_changes": has_unanalyzed_changes,
            "requires_ai_analysis": requires_ai_analysis,
            "repository_version": await self._current_repository_version(
                project_id
            ),
        }

    async def analyze_project_requirements(
        self,
        owner_id: UUID,
        project_id: UUID,
    ) -> dict:

        await self._require_project(
            owner_id,
            project_id,
        )

        requirements = await self.repo.list_requirements(
            project_id,
            None,
            None,
            None,
        )

        if not requirements:
            emptied_snapshot = await self._create_repository_snapshot(
                owner_id,
                project_id,
            )

            await self.db.commit()
            return {
                "total": 0,
                "saved": 0,
                "ai_analyzed": 0,
                "repository_version": (
                    emptied_snapshot["version_number"]
                    if emptied_snapshot
                    else await self._current_repository_version(project_id)
                ),
                "repository_version_created": bool(emptied_snapshot),
                "repository_version_error": self._last_snapshot_error,
                "results": [],
                "ai_results": [],
            }

        # -----------------------------------------------------------
        # MATERIALIZE THE REVIEWED REQUIREMENT ONLY WHEN ANALYZE IS
        # CLICKED.
        #
        # Accept stores the revised text as a draft. Reject stores the
        # review as ignored and the final OK changes the requirement
        # status to rejected. Neither action creates a new version.
        # The next explicit Analyze click creates the next repository
        # version and then runs Rule Engine + AI on that version.
        # -----------------------------------------------------------

               # Create a new requirement version only when an accepted
        # draft contains text different from the current version.

        reviewed_requirements = []

        for req in requirements:
            draft_text = str(
                req.get("draft_requirement_text") or ""
            ).strip()

            current_text = str(
                req.get("current_requirement_text")
                or req.get("text")
                or ""
            ).strip()

            if draft_text and draft_text != current_text:
                reviewed_requirements.append(req)

        if reviewed_requirements:
            for req in reviewed_requirements:
                requirement_id = UUID(str(req["id"]))

                await self.repo.lock_requirement_for_versioning(
                    requirement_id
                )

                next_number = await self.repo.next_version_number(
                    requirement_id
                )

                draft_text = str(
                    req.get("draft_requirement_text") or ""
                ).strip()

                await self.repo.create_version(
                    requirement_id=requirement_id,
                    version_number=next_number,
                    requirement_text=draft_text,
                    change_summary="Requirement updated from accepted AI suggestion.",
                    created_by=owner_id,
                )

                await self.repo.clear_requirement_draft_text(
                    requirement_id,
                    project_id,
                )

                await self.repo.update_requirement_status(
                    requirement_id,
                    project_id,
                    "pending",
                )

            await self.db.flush()

            requirements = await self.repo.list_requirements(
                project_id,
                None,
                None,
                None,
            )

        # -----------------------------------------------------------
        # CHECK FOR AN EXISTING COMPLETE ANALYSIS FIRST.
        #
        # If every current requirement version already has an AI
        # analysis saved, this request is only a read operation.
        # Do NOT run Rule Engine or call Groq again.
        # -----------------------------------------------------------

        cached_versions_result = await self.db.execute(
            text(
                """
                SELECT
                    r.id AS requirement_id,
                    v.id AS requirement_version_id,
                    v.version_number
                FROM requirements r
                INNER JOIN LATERAL (
                    SELECT id, version_number
                    FROM requirement_versions rv
                    WHERE rv.requirement_id = r.id
                    ORDER BY version_number DESC
                    LIMIT 1
                ) v ON TRUE
                WHERE r.project_id = :project_id
                ORDER BY r.requirement_code ASC
                """
            ),
            {"project_id": project_id},
        )

        current_versions = [
            dict(row)
            for row in cached_versions_result.mappings().all()
        ]

        cached_analysis_result = await self.db.execute(
            text(
                """
                SELECT DISTINCT rv.requirement_id
                FROM requirement_versions rv
                INNER JOIN ai_analysis aa
                    ON aa.requirement_version_id = rv.id
                INNER JOIN requirements r
                    ON r.id = rv.requirement_id
                WHERE r.project_id = :project_id
                  AND rv.version_number = (
                      SELECT MAX(rv2.version_number)
                      FROM requirement_versions rv2
                      WHERE rv2.requirement_id = rv.requirement_id
                  )
                  AND COALESCE(
                      jsonb_array_length(
                          COALESCE(
                              aa.raw_response_json -> 'suggestions',
                              '[]'::jsonb
                          )
                      ),
                      0
                  ) = (
                      SELECT COUNT(*)
                      FROM ai_suggestions ais
                      WHERE ais.ai_analysis_id = aa.id
                  )
                """
            ),
            {"project_id": project_id},
        )

        analyzed_requirement_ids = {
            UUID(str(row["requirement_id"]))
            for row in cached_analysis_result.mappings().all()
        }

        current_requirement_ids = {
            UUID(str(row["requirement_id"]))
            for row in current_versions
        }

        if current_requirement_ids and current_requirement_ids == analyzed_requirement_ids:
            # -------------------------------------------------------
            # Everything is already analyzed. Load the saved results
            # directly from the database. Nothing is recalculated.
            # -------------------------------------------------------
            cached_results = []
            cached_ai_results = []
            cached_saved_count = 0

            for current in current_versions:
                requirement_id = UUID(str(current["requirement_id"]))
                requirement_version_id = UUID(
                    str(current["requirement_version_id"])
                )

                validation_result = await self.db.execute(
                    text(
                        """
                        SELECT
                            id,
                            requirement_version_id,
                            rule_name,
                            passed,
                            message,
                            severity,
                            evaluated_at
                        FROM rule_validation
                        WHERE requirement_version_id = :requirement_version_id
                        ORDER BY evaluated_at ASC, rule_name ASC
                        """
                    ),
                    {
                        "requirement_version_id": requirement_version_id,
                    },
                )

                findings = [
                    {
                        "id": str(row["id"]),
                        "rule_name": row["rule_name"],
                        "passed": bool(row["passed"]),
                        "message": row["message"],
                        "severity": row["severity"],
                        "evaluated_at": row["evaluated_at"],
                    }
                    for row in validation_result.mappings().all()
                ]

                cached_saved_count += len(findings)

                cached_results.append(
                    {
                        "id": str(requirement_id),
                        "findings": findings,
                        "cached": True,
                    }
                )

                ai_result = await self.db.execute(
                    text(
                        """
                        SELECT
                            id,
                            requirement_version_id,
                            model_name,
                            prompt_type,
                            analysis_summary,
                            recommendations,
                            raw_response_json,
                            ambiguity_detected,
                            created_at
                        FROM ai_analysis aa                        WHERE requirement_version_id = :requirement_version_id
                      AND COALESCE(
                          jsonb_array_length(
                              COALESCE(
                                  aa.raw_response_json -> 'suggestions',
                                  '[]'::jsonb
                              )
                          ),
                          0
                      ) = (
                          SELECT COUNT(*)
                          FROM ai_suggestions ais
                          WHERE ais.ai_analysis_id = aa.id
                      )                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "requirement_version_id": requirement_version_id,
                    },
                )

                cached_analysis = ai_result.mappings().first()

                if cached_analysis:
                    suggestion_result = await self.db.execute(
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
                        {"ai_analysis_id": cached_analysis["id"]},
                    )

                    cached_suggestions = [
                        dict(row)
                        for row in suggestion_result.mappings().all()
                    ]

                    cached_ai_results.append(
                        {
                            "requirement_id": str(requirement_id),
                            "analysis": dict(cached_analysis),
                            "suggestions": cached_suggestions,
                            "cached": True,
                        }
                    )

            # Nothing needed AI, but the project may still differ from the
            # last version (document deleted, requirement approved).
            # Returns None when nothing changed, so no duplicates.
            cached_snapshot = await self._create_repository_snapshot(
                owner_id,
                project_id,
            )

            await self.db.commit()

            print(
                f"[ANALYSIS] Using saved Rule Engine + AI results for "
                f"project {project_id}. No re-analysis required."
            )

            return {
                "total": len(current_versions),
                "saved": cached_saved_count,
                "ai_analyzed": len(cached_ai_results),
                "repository_version": (
                    cached_snapshot["version_number"]
                    if cached_snapshot
                    else await self._current_repository_version(project_id)
                ),
                "repository_version_created": bool(cached_snapshot),
                "repository_version_error": self._last_snapshot_error,
                "results": cached_results,
                "ai_results": cached_ai_results,
                "cached": True,
                "analysis_available": True,
                "has_unanalyzed_changes": False,
                "requires_ai_analysis": False,
            }

        from services.rule_engine import analyze_requirements

        rule_engine_input = []

        for req in requirements:
            requirement_text = req.get(
                "current_requirement_text"
            )

            if requirement_text is None:
                requirement_text = req.get(
                    "text",
                    "",
                )

            rule_engine_input.append(
                {
                    "id": str(req["id"]),
                    "text": requirement_text or "",
                }
            )

        results = analyze_requirements(
            rule_engine_input
        )

        if not results:
            await self.db.commit()

            return {
                "total": 0,
                "saved": 0,
                "results": [],
            }

        # -----------------------------------------------------------
        # Fetch the latest version for all requirements in ONE query.
        # -----------------------------------------------------------

        requirement_ids = [
            UUID(str(result["id"]))
            for result in results
        ]

        version_result = await self.db.execute(
            text(
                """
                SELECT DISTINCT ON (requirement_id)
                    id,
                    requirement_id,
                    version_number
                FROM requirement_versions
                WHERE requirement_id IN :requirement_ids
                ORDER BY
                    requirement_id,
                    version_number DESC
                """
            ).bindparams(
                bindparam(
                    "requirement_ids",
                    expanding=True,
                )
            ),
            {
                "requirement_ids": requirement_ids,
            },
        )

        latest_versions = {
            row["requirement_id"]: row["id"]
            for row in version_result.mappings()
        }

        if not latest_versions:
            
            await self.db.commit()

            return {
                "total": len(results),
                "saved": 0,
                "results": results,
            }

        # -----------------------------------------------------------
        # Delete all old validation rows in ONE query.
        # -----------------------------------------------------------

        version_ids = list(
            latest_versions.values()
        )

        await self.db.execute(
            text(
                """
                DELETE FROM rule_validation
                WHERE requirement_version_id IN :version_ids
                """
            ).bindparams(
                bindparam(
                    "version_ids",
                    expanding=True,
                )
            ),
            {
                "version_ids": version_ids,
            },
        )

        # -----------------------------------------------------------
        # Prepare all validation rows in memory.
        # -----------------------------------------------------------

        validation_rows = []

        for result in results:
            requirement_id = UUID(
                str(result["id"])
            )

            requirement_version_id = (
                latest_versions.get(
                    requirement_id
                )
            )

            if requirement_version_id is None:
                continue

            for finding in result.get(
                "findings",
                [],
            ):
                validation_rows.append(
                    {
                        "requirement_version_id": (
                            requirement_version_id
                        ),
                        "rule_name": (
                            finding.get("rule_name")
                            or "Unknown Rule"
                        ),
                        "passed": bool(
                            finding.get(
                                "passed",
                                False,
                            )
                        ),
                        "message": (
                            finding.get("message")
                            or finding.get(
                                "description",
                                "",
                            )
                        ),
                        "severity": finding.get(
                            "severity"
                        ),
                    }
                )

        # -----------------------------------------------------------
        # Insert all findings in ONE executemany operation.
        # -----------------------------------------------------------

        if validation_rows:
            await self.db.execute(
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
                    """
                ),
                validation_rows,
            )

        saved_count = len(validation_rows)

        # -----------------------------------------------------------
        # AI ANALYSIS
        # Rule Engine has completed. AI analysis uses the requirement
        # text and the Rule Engine findings as additional context.
        # -----------------------------------------------------------

        ai_results = []
        master_rules = self._load_master_rules_for_ai()

        for result in results:
            requirement_id = UUID(str(result["id"]))

            requirement_version_id = latest_versions.get(
                requirement_id
            )

            if requirement_version_id is None:
                continue

            requirement_text = next(
                (
                    req.get("current_requirement_text")
                    or req.get("text")
                    or ""
                    for req in requirements
                    if UUID(str(req["id"])) == requirement_id
                ),
                "",
            )

            rule_findings = result.get("findings", [])

            # Do not create duplicate AI analyses when the latest
            # requirement version has already been analyzed successfully.
            cached_analysis_result = await self.db.execute(
                text(
                    """
                    SELECT
                        id,
                        requirement_version_id,
                        model_name,
                        prompt_type,
                        analysis_summary,
                        recommendations,
                        raw_response_json,
                        ambiguity_detected,
                        created_at
                    FROM ai_analysis aa                    WHERE requirement_version_id = :requirement_version_id
                      AND COALESCE(
                          jsonb_array_length(
                              COALESCE(
                                  aa.raw_response_json -> 'suggestions',
                                  '[]'::jsonb
                              )
                          ),
                          0
                      ) = (
                          SELECT COUNT(*)
                          FROM ai_suggestions ais
                          WHERE ais.ai_analysis_id = aa.id
                      )                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"requirement_version_id": requirement_version_id},
            )

            cached_analysis = cached_analysis_result.mappings().first()

            if cached_analysis:
                suggestion_result = await self.db.execute(
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
                    {"ai_analysis_id": cached_analysis["id"]},
                )

                cached_suggestions = [
                    dict(row)
                    for row in suggestion_result.mappings()
                ]

                ai_results.append(
                    {
                        "requirement_id": str(requirement_id),
                        "analysis": dict(cached_analysis),
                        "suggestions": cached_suggestions,
                        "cached": True,
                    }
                )
                print(
                    f"[AI ANALYSIS] Using cached analysis for requirement "
                    f"{requirement_id}"
                )
                continue

            try:
                current_version_number = next(
                    (
                        int(item.get("version_number") or 0)
                        for item in current_versions
                        if UUID(str(item["requirement_id"])) == requirement_id
                    ),
                    1,
                )

                resolve_failed_requirement = current_version_number > 1

                ai_result = await self.ai_analysis.analyze_requirement(
                    requirement_text=requirement_text,
                    rule_findings=rule_findings,
                    master_rules=master_rules,
                    resolve_failed_requirement=resolve_failed_requirement,
                )

                ai_analysis_row = await self.repo.create_ai_analysis(
                    requirement_version_id=requirement_version_id,
                    model_name="openai/gpt-oss-20b",
                    prompt_type="requirement_quality_analysis",
                    analysis_summary=ai_result.analysis_summary,
                    recommendations=json.dumps(
                        ai_result.issues,
                        ensure_ascii=False,
                    ),
                    raw_response_json=ai_result.model_dump(),
                    ambiguity_detected=ai_result.ambiguity_detected,
                )

                saved_suggestions = []

                for suggestion in ai_result.suggestions:
                    suggestion_row = await self.repo.create_ai_suggestion(
                        ai_analysis_id=ai_analysis_row["id"],
                        suggestion_text=suggestion.suggestion_text,
                        suggestion_type=suggestion.suggestion_type,
                        resolved_text=suggestion.resolved_requirement_text,
                    )

                    saved_suggestions.append(suggestion_row)

                ai_results.append(
                    {
                        "requirement_id": str(requirement_id),
                        "analysis": ai_analysis_row,
                        "suggestions": saved_suggestions,
                    }
                )

            except Exception as exc:
                print(
                    f"[AI ANALYSIS] Failed for requirement "
                    f"{requirement_id}: {exc}"
                )

                ai_results.append(
                    {
                        "requirement_id": str(requirement_id),
                        "error": str(exc),
                    }
                )

                # A requirement is completed only when the actual Rule Engine
        # has no failed findings and the AI produced no suggestion.
        for result in results:
            requirement_id = UUID(str(result["id"]))
            # Clean = no BLOCKING finding (failed Check category or
            # High-severity Issue). Medium/Low issues stay visible but
            # do not block approval.
            failed_findings = [
                finding
                for finding in result.get("findings", [])
                if is_blocking_finding(finding)
            ]

            current_status = str(
                next(
                    (
                        req.get("status")
                        for req in requirements
                        if str(req.get("id")) == str(requirement_id)
                    ),
                    "pending",
                )
                or "pending"
            ).strip().lower()

            ai_item = next(
                (
                    item
                    for item in ai_results
                    if str(item.get("requirement_id"))
                    == str(requirement_id)
                ),
                None,
            )

            suggestions = (
                ai_item.get("suggestions", [])
                if ai_item
                else []
            )

            if (
                ai_item
                and "analysis" in ai_item
                and not failed_findings
                and current_status == "pending"
            ):
                await self.repo.update_requirement_status(
                    requirement_id,
                    project_id,
                    "approved",
                )

        # Create repository version after successful fresh AI analysis.
        fresh_ai_results = [
            item for item in ai_results
            if "analysis" in item and not item.get("cached")
        ]

        fresh_ai_errors = [
            item for item in ai_results
            if "error" in item and not item.get("cached")
        ]
        
        repository_snapshot = None
        self._last_snapshot_error = None
        snapshot_skipped_reason = None

        # Create a version only when the analysis finished without AI
        # errors. If one requirement failed (e.g. a Groq limit) no version
        # is created; the next Analyze re-uses saved results, analyzes the
        # missing ones, and then creates it.
        if not fresh_ai_errors:
            repository_snapshot = await self._create_repository_snapshot(
                owner_id,
                project_id,
            )
        else:
            snapshot_skipped_reason = (
                f"{len(fresh_ai_errors)} requirement(s) failed AI analysis "
                "(e.g. Groq limit). Run Analyze again to retry; the "
                "repository version is created once all succeed."
            )
            print(f"[REPOSITORY VERSION] Skipped: {snapshot_skipped_reason}")

        await self.db.commit()

        return {
            "total": len(results),
            "saved": saved_count,
            "ai_analyzed": len(
                [
                    item
                    for item in ai_results
                    if "analysis" in item
                ]
            ),
            "repository_version": (
                repository_snapshot["version_number"]
                if repository_snapshot
                else await self._current_repository_version(project_id)
            ),
            "repository_version_created": bool(repository_snapshot),
            "repository_version_skipped_reason": snapshot_skipped_reason,
            "repository_version_error": self._last_snapshot_error,
            "results": results,
            "ai_results": ai_results,
        }

    # ---------------------------------------------------------------
    # AI suggestion / requirement review actions
    # ---------------------------------------------------------------

    # ---------------------------------------------------------------
    # Issue waivers (BA accepts an issue as-is)
    # ---------------------------------------------------------------

    async def _load_waivers(
        self,
        version_ids: list[UUID],
    ) -> dict[str, dict[str, str]]:
        """{requirement_version_id: {rule_name_lower: reason}}."""

        if not version_ids:
            return {}

        try:
            async with self.db.begin_nested():
                result = await self.db.execute(
                    text(
                        """
                        SELECT requirement_version_id, rule_name, reason
                        FROM requirement_issue_waivers
                        WHERE requirement_version_id IN :version_ids
                        """
                    ).bindparams(
                        bindparam("version_ids", expanding=True)
                    ),
                    {"version_ids": version_ids},
                )
                rows = result.mappings().all()
        except Exception as exc:
            print(f"[WAIVERS] Could not load waivers: {exc}")
            return {}

        waivers: dict[str, dict[str, str]] = {}

        for row in rows:
            waivers.setdefault(
                str(row["requirement_version_id"]), {}
            )[str(row["rule_name"]).strip().lower()] = (
                row["reason"] or ""
            )

        return waivers

    async def set_issue_waiver(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
        rule_name: str,
        waive: bool,
        reason: str | None = None,
    ) -> dict:
        """
        Waive (or un-waive) one failed finding of the requirement's
        CURRENT version, then re-evaluate its review status:
        no blocking finding left -> approved; blocking again -> pending.
        Rejected requirements and requirements with an unanalyzed draft
        are never changed.
        """

        await self._require_project(owner_id, project_id)
        await self._require_requirement(project_id, requirement_id)

        rule_name = str(rule_name or "").strip()

        if not rule_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="rule_name is required.",
            )

        version_row = (
            await self.db.execute(
                text(
                    """
                    SELECT id
                    FROM requirement_versions
                    WHERE requirement_id = :requirement_id
                    ORDER BY version_number DESC
                    LIMIT 1
                    """
                ),
                {"requirement_id": requirement_id},
            )
        ).mappings().first()

        if version_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement version not found.",
            )

        version_id = version_row["id"]

        findings = [
            dict(row)
            for row in (
                await self.db.execute(
                    text(
                        """
                        SELECT rule_name, passed, severity
                        FROM rule_validation
                        WHERE requirement_version_id = :version_id
                        """
                    ),
                    {"version_id": version_id},
                )
            ).mappings().all()
        ]

        target = next(
            (
                item
                for item in findings
                if str(item["rule_name"]).strip().lower()
                == rule_name.lower()
                and not item["passed"]
            ),
            None,
        )

        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No failed finding with that name on the "
                "current version.",
            )

        if waive:
            await self.db.execute(
                text(
                    """
                    INSERT INTO requirement_issue_waivers
                        (requirement_version_id, rule_name, reason,
                         created_by)
                    VALUES
                        (:version_id, :rule_name, :reason, :created_by)
                    ON CONFLICT (requirement_version_id, rule_name)
                    DO UPDATE SET reason = EXCLUDED.reason
                    """
                ),
                {
                    "version_id": version_id,
                    "rule_name": target["rule_name"],
                    "reason": (reason or "").strip() or None,
                    "created_by": owner_id,
                },
            )
        else:
            await self.db.execute(
                text(
                    """
                    DELETE FROM requirement_issue_waivers
                    WHERE requirement_version_id = :version_id
                      AND LOWER(rule_name) = LOWER(:rule_name)
                    """
                ),
                {
                    "version_id": version_id,
                    "rule_name": target["rule_name"],
                },
            )

        waived_names = set(
            (await self._load_waivers([version_id]))
            .get(str(version_id), {})
            .keys()
        )

        rules = await asyncio.to_thread(self._load_master_rules_for_ai)
        modes = {
            str(rule.get("category_name") or "").strip().lower():
            str(rule.get("evaluation_mode") or "").strip().lower()
            for rule in rules
        }

        blocking_remaining = [
            item
            for item in findings
            if not item["passed"]
            and is_blocking_finding(
                {
                    "passed": False,
                    "waived": str(item["rule_name"]).strip().lower()
                    in waived_names,
                    "evaluation_mode": modes.get(
                        str(item["rule_name"]).strip().lower()
                    ),
                    "severity": item["severity"],
                }
            )
        ]

        requirement_row = (
            await self.db.execute(
                text(
                    """
                    SELECT status, draft_requirement_text
                    FROM requirements
                    WHERE id = :requirement_id
                      AND project_id = :project_id
                    """
                ),
                {
                    "requirement_id": requirement_id,
                    "project_id": project_id,
                },
            )
        ).mappings().first()

        current_status = str(
            (requirement_row or {}).get("status") or "pending"
        ).strip().lower()
        has_draft = bool(
            str(
                (requirement_row or {}).get("draft_requirement_text")
                or ""
            ).strip()
        )
        new_status = current_status

        if not has_draft:
            if not blocking_remaining and current_status == "pending":
                new_status = "approved"
            elif blocking_remaining and current_status == "approved":
                new_status = "pending"

        if new_status != current_status:
            await self.repo.update_requirement_status(
                requirement_id,
                project_id,
                new_status,
            )

        await self.db.commit()

        return {
            "requirement_id": str(requirement_id),
            "rule_name": target["rule_name"],
            "waived": waive,
            "status": new_status,
            "blocking_remaining": len(blocking_remaining),
        }

    async def accept_ai_suggestion(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
        suggestion_id: UUID,
    ) -> dict:
        await self._require_project(owner_id, project_id)
        await self._require_requirement(project_id, requirement_id)

        suggestion = await self.repo.get_ai_suggestion_for_requirement(
            requirement_id,
            suggestion_id,
        )

        if not suggestion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI suggestion not found for this requirement.",
            )

        if str(suggestion.get("status") or "pending").lower() != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This AI suggestion has already been reviewed.",
            )

        resolved_text = str(
            suggestion.get("resolved_text") or ""
        ).strip()

        if not resolved_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This AI suggestion does not contain a revised requirement text.",
            )

        # Accept only creates a draft. The repository version stays
        # unchanged until the next explicit Analyze click.
        updated_requirement = await self.repo.set_requirement_draft_text(
            requirement_id=requirement_id,
            project_id=project_id,
            draft_requirement_text=resolved_text,
        )

        updated_suggestion = await self.repo.update_ai_suggestion_status(
            suggestion_id=suggestion_id,
            status="accepted",
            reviewed_by=owner_id,
        )

        await self.db.commit()

        updated_requirement = await self.repo.get_requirement(
            requirement_id,
            project_id,
        )

        return {
            "requirement": updated_requirement,
            "suggestion": updated_suggestion,
            "version": None,
            "version_created": False,
            "analysis_required": True,
        }

    async def reject_ai_suggestion(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
        suggestion_id: UUID,
    ) -> dict:
        await self._require_project(owner_id, project_id)
        await self._require_requirement(project_id, requirement_id)

        suggestion = await self.repo.get_ai_suggestion_for_requirement(
            requirement_id,
            suggestion_id,
        )

        if not suggestion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI suggestion not found for this requirement.",
            )

        if str(suggestion.get("status") or "pending").lower() != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This AI suggestion has already been reviewed.",
            )

        updated_suggestion = await self.repo.update_ai_suggestion_status(
            suggestion_id=suggestion_id,
            status="ignored",
            reviewed_by=owner_id,
        )

        await self.db.commit()

        return {
            "suggestion": updated_suggestion,
            "analysis_required": True,
            "version_created": False,
        }

    async def approve_requirement(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
    ) -> dict:
        await self._require_project(owner_id, project_id)
        requirement = await self._require_requirement(
            project_id,
            requirement_id,
        )

        updated = await self.repo.update_requirement_status(
            requirement_id,
            project_id,
            "approved",
        )

        await self.db.commit()

        return {
            "requirement": updated,
            "version_created": False,
            "analysis_required": True,
        }

    async def reject_requirement(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
    ) -> dict:
        await self._require_project(owner_id, project_id)
        requirement = await self._require_requirement(
            project_id,
            requirement_id,
        )

        updated = await self.repo.update_requirement_status(
            requirement_id,
            project_id,
            "rejected",
        )

        await self.db.commit()

        return {
            "requirement": updated,
            "version_created": False,
            "analysis_required": True,
        }

    # ---------------------------------------------------------------
    # Versions
    # ---------------------------------------------------------------

    async def create_version(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
        payload: RequirementVersionCreate,
    ) -> RequirementVersionResponse:

        await self._require_project(
            owner_id,
            project_id,
        )

        await self._require_requirement(
            project_id,
            requirement_id,
        )

        await self.repo.lock_requirement_for_versioning(
            requirement_id
        )

        next_number = await self.repo.next_version_number(
            requirement_id
        )

        version = await self.repo.create_version(
            requirement_id=requirement_id,
            version_number=next_number,
            requirement_text=payload.requirement_text,
            change_summary=payload.change_summary,
            created_by=owner_id,
        )

        return RequirementVersionResponse.model_validate(
            version
        )

    async def list_versions(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
    ) -> list[RequirementVersionResponse]:

        await self._require_project(
            owner_id,
            project_id,
        )

        await self._require_requirement(
            project_id,
            requirement_id,
        )

        rows = await self.repo.list_versions(
            requirement_id
        )

        return [
            RequirementVersionResponse.model_validate(row)
            for row in rows
        ]
    async def delete_source(
        self,
        user_id: UUID,
        project_id: UUID,
        source_id: UUID,
    ) -> None:
        await self._require_project(user_id, project_id)

        source = await self.repo.get_source(source_id, project_id)
        if not source:
            raise ValueError("Source not found")

        await self.repo.delete_source_cascade(
            source_id=source_id,
        )

        await self.db.commit()

    async def analyze_traceability_impact(
        self,
        owner_id: UUID,
        project_id: UUID,
        requirement_id: UUID,
    ) -> dict:
        await self._require_project(owner_id, project_id)

        source = await self.repo.get_requirement(
            requirement_id,
            project_id,
        )

        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requirement not found.",
            )

        source_version_id = source.get("current_version_id")
        existing_items = await self.repo.list_change_impacts(
            source_version_id
        )

        if existing_items:
            return {
                "requirement_id": str(requirement_id),
                "current_version_id": str(source_version_id),
                "saved": len(existing_items),
                "items": existing_items,
                "cached": True,
                "message": "Impact analysis already exists for this version.",
            }
        if not source_version_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Analyze the requirement first to create its version.",
            )

        all_requirements = await self.repo.list_requirements(
            project_id, None, None, None
        )

        all_links = await self.repo.list_project_traceability_links(
            project_id=project_id
        )

        source_id = str(requirement_id)

        related_ids = set()

        for link in all_links:
            link_source = str(link.get("source_requirement_id"))
            link_target = str(link.get("target_requirement_id"))

            if link_source == source_id:
                related_ids.add(link_target)
            elif link_target == source_id:
                related_ids.add(link_source)

        if not related_ids:
            return {
                "requirement_id": source_id,
                "impact_level": "Not set",
                "message": "No traceability links found.",
                "saved": 0,
                "items": [],
            }

        affected_requirements = [
            req for req in all_requirements
            if str(req["id"]) in related_ids
        ]

        impacts = await self.ai_analysis.analyze_traceability_impact(
            source_requirement=source,
            affected_requirements=affected_requirements,
            traceability_links=all_links,
        )

        saved_items = []

        try:
            for impact in impacts:
                saved = await self.repo.save_change_impact(
                    source_requirement_version_id=source_version_id,
                    affected_requirement_id=UUID(
                        impact["affected_requirement_id"]
                    ),
                    risk_level=impact["risk_level"],
                    impact_description=impact["impact_description"],
                    ai_generated=True,
                )
                saved_items.append(saved)

            await self.db.commit()

        except Exception:
            await self.db.rollback()
            raise

        return {
            "requirement_id": source_id,
            "current_version_id": str(source_version_id),
            "saved": len(saved_items),
            "items": saved_items,
        }
