from fastapi import APIRouter, HTTPException

from app.modules.outage_credit import CreditError, GrossReadingMissing
from app.schemas.credits import CreditCreate, CreditOut, CreditVoid
from app.services.billing_service import BillingService

router = APIRouter(tags=["outage-credits"])


def _credit_error(err: CreditError):
    """把领域错误映射成可读 HTTP 错误；超额错误附带差额明细。"""
    detail = err.to_detail() if hasattr(err, "to_detail") else {"message": str(err)}
    raise HTTPException(status_code=422, detail=detail)


@router.get("/accounts/{account_id}/credits")
def list_credits(account_id: int, period: str | None = None):
    with BillingService() as svc:
        if not svc.get_account(account_id):
            raise HTTPException(404, "account not found")
        items = svc.list_credits(account_id, period)
    active_total = round(sum(c["kwh"] for c in items if c["active"]), 3)
    return {"items": items, "active_total": active_total}


@router.post("/accounts/{account_id}/credits")
def register_credit(account_id: int, body: CreditCreate):
    if body.account_id != account_id:
        raise HTTPException(status_code=400, detail={"message": "路径户号与请求体户号不一致"})
    with BillingService() as svc:
        try:
            return svc.register_credit(body.account_id, body.period, body.kwh, body.reason)
        except GrossReadingMissing as e:
            raise HTTPException(status_code=409, detail={"message": str(e)})
        except CreditError as e:
            _credit_error(e)


@router.post("/credits/{credit_id}/void", response_model=CreditOut)
def void_credit(credit_id: int, body: CreditVoid):
    with BillingService() as svc:
        try:
            return svc.void_credit(credit_id, body.reason)
        except CreditError as e:
            raise HTTPException(status_code=422, detail={"message": str(e)})
