from pydantic import BaseModel, Field


class CreditCreate(BaseModel):
    period: str = Field(min_length=1)
    kwh: float = Field(gt=0)
    note: str | None = None


class CreditVoid(BaseModel):
    note: str | None = None
