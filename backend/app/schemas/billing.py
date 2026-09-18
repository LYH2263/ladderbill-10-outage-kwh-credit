from pydantic import BaseModel, Field


class BillRequest(BaseModel):
    account_id: int | None = None
    period: str | None = None
    kwh: float | None = Field(default=None, ge=0)
    peak: bool = False
    persist: bool = True


class CompareRequest(BaseModel):
    kwh: float = Field(ge=0)
    persist: bool = False


class CalcRunOut(BaseModel):
    id: int
    kind: str
    account_id: int | None
    input_json: str
    result_json: str
    created_at: str
