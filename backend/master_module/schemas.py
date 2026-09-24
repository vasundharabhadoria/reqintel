from pydantic import BaseModel, Field
from typing import Optional


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_active: bool


class RuleCreate(BaseModel):
    category_id: str
    rule: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    why_it_matters: Optional[str] = None
    recommendation: Optional[str] = None
    rule_type: str = "Keyword"
    severity: str = "Medium"
    is_active: bool = True


class RuleUpdate(BaseModel):
    category_id: Optional[str] = None
    rule: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    description: Optional[str] = None
    why_it_matters: Optional[str] = None
    recommendation: Optional[str] = None
    rule_type: Optional[str] = None
    severity: Optional[str] = None
    is_active: Optional[bool] = None


class RuleResponse(BaseModel):
    id: str
    category_id: str
    rule: str
    description: Optional[str] = None
    why_it_matters: Optional[str] = None
    recommendation: Optional[str] = None
    rule_type: str
    severity: str
    is_active: bool