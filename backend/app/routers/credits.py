from fastapi import APIRouter, HTTPException

from app.schemas.credits import CreditCreate, CreditVoid
from app.services.billing_service import BillingService, CreditError

router = APIRouter(tags=["credits"])


@router.get("/accounts/{account_id}/credits")
def list_credits(account_id: int, period: str | None = None):
    with BillingService() as svc:
        if not svc.get_account(account_id):
            raise HTTPException(404, {"message": "account not found", "code": "account_not_found"})
        items = svc.list_credits(account_id, period)
        if period:
            summary = svc.period_summary(account_id, period)
            return {
                "items": items,
                "gross_kwh": summary["gross_kwh"],
                "credit_kwh": summary["credit_kwh"],
                "net_kwh": summary["net_kwh"],
            }
        return {"items": items}


@router.get("/accounts/{account_id}/credits/summary")
def credit_summary(account_id: int, period: str):
    with BillingService() as svc:
        try:
            return svc.period_summary(account_id, period)
        except CreditError as exc:
            raise HTTPException(status_code=404 if exc.code == "account_not_found" else 409,
                                detail={"message": exc.message, "code": exc.code, **exc.extra})


@router.post("/accounts/{account_id}/credits", status_code=201)
def create_credit(account_id: int, body: CreditCreate):
    with BillingService() as svc:
        try:
            return svc.register_credit(account_id, body.period.strip(), body.kwh, body.note)
        except CreditError as exc:
            status = 404 if exc.code == "account_not_found" else 409
            raise HTTPException(status_code=status,
                                detail={"message": exc.message, "code": exc.code, **exc.extra})


@router.post("/credits/{credit_id}/void")
def void_credit(credit_id: int, body: CreditVoid):
    with BillingService() as svc:
        try:
            return {"credit": svc.void_credit(credit_id, body.note)}
        except CreditError as exc:
            status = 404 if exc.code == "credit_not_found" else 409
            raise HTTPException(status_code=status,
                                detail={"message": exc.message, "code": exc.code, **exc.extra})
