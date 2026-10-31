
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth.schemas import UserResponse
from core.dependencies import get_current_user
from db.session import get_db
from services.requirement_service import RequirementService


router = APIRouter(
    prefix="/api/v1/projects/{project_id}/requirements",
    tags=["Change Impact"],
)


@router.get("/{requirement_id}/impact")
async def get_change_impact(
    project_id: UUID,
    requirement_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    requirement = await service.get_requirement(
        UUID(current_user.id),
        project_id,
        requirement_id,
    )

    current_version_id = requirement.current_version_id

    if not current_version_id:
        return {
            "requirement_id": str(requirement.id),
            "current_version_id": None,
            "items": [],
            "total": 0,
        }

    result = await db.execute(
        text(
            """
            SELECT
                cia.id,
                cia.source_requirement_version_id,
                cia.affected_requirement_id,
                cia.affected_module_id,
                cia.affected_api_id,
                cia.affected_test_case_id,
                cia.risk_level,
                cia.impact_description,
                cia.ai_generated,
                cia.created_at,
                r.requirement_code AS affected_requirement_code,
                r.title AS affected_requirement_title,
                v.requirement_text AS affected_requirement_text
            FROM change_impact_analysis cia
            INNER JOIN requirements r
                ON r.id = cia.affected_requirement_id
               AND r.project_id = :project_id
            LEFT JOIN v_requirement_current_version v
                ON v.requirement_id = r.id
            WHERE cia.source_requirement_version_id = :version_id
            ORDER BY cia.created_at DESC
            """
        ),
        {
            "project_id": project_id,
            "version_id": current_version_id,
        },
    )

    items = [
        dict(row)
        for row in result.mappings().all()
    ]

    return {
        "requirement_id": str(requirement.id),
        "current_version_id": str(current_version_id),
        "items": items,
        "total": len(items),
    }

@router.post("/{requirement_id}/impact/analyze")
async def analyze_change_impact(
    project_id: UUID,
    requirement_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequirementService(db)

    return await service.analyze_traceability_impact(
        UUID(current_user.id),
        project_id,
        requirement_id,
    )
