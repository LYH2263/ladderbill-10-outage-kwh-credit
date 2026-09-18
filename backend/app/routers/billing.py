from fastapi import APIRouter, HTTPException

from app.schemas.billing import BillRequest, CompareRequest
from app.services.billing_service import BillingService, CreditError

router = APIRouter(tags=["billing"])


@router.post("/bill")
def post_bill(body: BillRequest):
    with BillingService() as svc:
        try:
            return svc.run_bill(
                body.kwh, body.peak, body.account_id, body.persist, period=body.period
            )
        except CreditError as exc:
            status = 404 if exc.code.endswith("_not_found") else 409
            raise HTTPException(status_code=status,
                                detail={"message": exc.message, "code": exc.code, **exc.extra})


@router.post("/compare")
def post_compare(body: CompareRequest):
    with BillingService() as svc:
        return svc.run_compare(body.kwh, body.persist)
