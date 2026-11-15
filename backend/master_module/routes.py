from fastapi import APIRouter, Depends, HTTPException, status
from postgrest import SyncPostgrestClient

from auth.schemas import UserResponse
from core.dependencies import get_current_user, get_user_db

from .schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    RuleCreate,
    RuleResponse,
    RuleUpdate,
)


router = APIRouter(
    prefix="/api/v1/master",
    tags=["Master Module"],
)


def require_admin(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required.",
        )

    return current_user


# =========================
# CATEGORIES
# =========================


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
)
def get_categories(
    current_user: UserResponse = Depends(require_admin),
    db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        response = (
            db
            .from_("rule_categories")
            .select(
                "id, name, description, evaluation_mode, is_active"
            )
            .order("name")
            .execute()
        )

        return response.data or []

    except Exception as exc:
        print("GET CATEGORIES ERROR:", repr(exc))

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch rule categories.",
        ) from exc


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    payload: CategoryCreate,
    current_user: UserResponse = Depends(require_admin),
    db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        response = (
            db
            .from_("rule_categories")
            .insert(
                {
                    "name": payload.name.strip(),
                    "description": (
                        payload.description.strip()
                        if payload.description
                        else None
                    ),
                    "evaluation_mode": payload.evaluation_mode,
                }
            )
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to create category.",
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as exc:
        print("CREATE CATEGORY ERROR:", repr(exc))

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create category.",
        ) from exc


@router.put(
    "/categories/{category_id}",
    response_model=CategoryResponse,
)
def update_category(
    category_id: str,
    payload: CategoryUpdate,
    current_user: UserResponse = Depends(require_admin),
    db: SyncPostgrestClient = Depends(get_user_db),
):
    update_data = {}

    if payload.name is not None:
        update_data["name"] = payload.name.strip()

    if payload.description is not None:
        update_data["description"] = payload.description.strip()

    if payload.evaluation_mode is not None:
        update_data["evaluation_mode"] = payload.evaluation_mode

    if payload.is_active is not None:
        update_data["is_active"] = payload.is_active

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields were provided for update.",
        )

    try:
        response = (
            db
            .from_("rule_categories")
            .update(update_data)
            .eq("id", category_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found.",
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as exc:
        print("UPDATE CATEGORY ERROR:", repr(exc))

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to update category.",
        ) from exc


@router.delete(
    "/categories/{category_id}",
)
def delete_category(
    category_id: str,
    current_user: UserResponse = Depends(require_admin),
    db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        response = (
            db
            .from_("rule_categories")
            .delete()
            .eq("id", category_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found.",
            )

        return {
            "message": "Category deleted successfully."
        }

    except HTTPException:
        raise

    except Exception as exc:
        print("DELETE CATEGORY ERROR:", repr(exc))

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to delete category.",
        ) from exc


# =========================
# RULES
# =========================


@router.get(
    "/rules",
    response_model=list[RuleResponse],
)
def get_rules(
    category_id: str | None = None,
    current_user: UserResponse = Depends(require_admin),
    db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        query = (
            db
            .from_("master_rules")
            .select(
                """
                id,
                category_id,
                rule,
                description,
                why_it_matters,
                recommendation,
                rule_type,
                severity,
                is_active
                """
            )
            .order("created_at")
        )

        if category_id:
            query = query.eq(
                "category_id",
                category_id,
            )

        response = query.execute()

        return response.data or []

    except Exception as exc:
        print("GET RULES ERROR:", repr(exc))

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch rules.",
        ) from exc


@router.post(
    "/rules",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rule(
    payload: RuleCreate,
    current_user: UserResponse = Depends(require_admin),
    db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        category_response = (
            db
            .from_("rule_categories")
            .select("id")
            .eq("id", payload.category_id)
            .single()
            .execute()
        )

        if not category_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found.",
            )

        response = (
            db
            .from_("master_rules")
            .insert(
                {
                    "category_id": payload.category_id,
                    "rule": payload.rule.strip(),
                    "description": (
                        payload.description.strip()
                        if payload.description
                        else None
                    ),
                    "why_it_matters": (
                        payload.why_it_matters.strip()
                        if payload.why_it_matters
                        else None
                    ),
                    "recommendation": (
                        payload.recommendation.strip()
                        if payload.recommendation
                        else None
                    ),
                    "rule_type": payload.rule_type,
                    "severity": payload.severity,
                    "is_active": payload.is_active,
                }
            )
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to create rule.",
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as exc:
        print("CREATE RULE ERROR:", repr(exc))

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create rule.",
        ) from exc


@router.put(
    "/rules/{rule_id}",
    response_model=RuleResponse,
)
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    current_user: UserResponse = Depends(require_admin),
    db: SyncPostgrestClient = Depends(get_user_db),
):
    update_data = {}

    if payload.category_id is not None:
        update_data["category_id"] = payload.category_id

    if payload.rule is not None:
        update_data["rule"] = payload.rule.strip()

    if payload.description is not None:
        update_data["description"] = payload.description.strip()

    if payload.why_it_matters is not None:
        update_data["why_it_matters"] = payload.why_it_matters.strip()

    if payload.recommendation is not None:
        update_data["recommendation"] = payload.recommendation.strip()

    if payload.rule_type is not None:
        update_data["rule_type"] = payload.rule_type

    if payload.severity is not None:
        update_data["severity"] = payload.severity

    if payload.is_active is not None:
        update_data["is_active"] = payload.is_active

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields were provided for update.",
        )

    try:
        response = (
            db
            .from_("master_rules")
            .update(update_data)
            .eq("id", rule_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rule not found.",
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as exc:
        print("UPDATE RULE ERROR:", repr(exc))

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to update rule.",
        ) from exc


@router.delete(
    "/rules/{rule_id}",
)
def delete_rule(
    rule_id: str,
    current_user: UserResponse = Depends(require_admin),
    db: SyncPostgrestClient = Depends(get_user_db),
):
    try:
        response = (
            db
            .from_("master_rules")
            .delete()
            .eq("id", rule_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rule not found.",
            )

        return {
            "message": "Rule deleted successfully."
        }

    except HTTPException:
        raise

    except Exception as exc:
        print("DELETE RULE ERROR:", repr(exc))

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to delete rule.",
        ) from exc