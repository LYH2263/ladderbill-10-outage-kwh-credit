import re

from pydantic import BaseModel, Field, field_validator

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class CreditCreate(BaseModel):
    account_id: int
    # 账期，格式 YYYY-MM
    period: str = Field(min_length=7, max_length=7)
    kwh: float = Field(gt=0)
    reason: str | None = None

    @field_validator("period")
    @classmethod
    def _check_period(cls, v: str) -> str:
        if not PERIOD_RE.match(v):
            raise ValueError("账期格式应为 YYYY-MM，例如 2026-09")
        return v


class CreditVoid(BaseModel):
    reason: str | None = None


class CreditOut(BaseModel):
    id: int
    account_id: int
    period: str
    kwh: float
    reason: str | None = None
    status: str
    active: bool
    voided_at: str | None = None
    void_reason: str | None = None
    created_at: str
