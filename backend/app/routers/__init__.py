from fastapi import APIRouter

from app.routers import (
    accounts,
    billing,
    credits,
    dashboard,
    history,
    readings,
    settings,
    tiers,
)

api = APIRouter(prefix="/api")
api.include_router(dashboard.router)
api.include_router(accounts.router)
api.include_router(credits.router)
api.include_router(tiers.router)
api.include_router(readings.router)
api.include_router(billing.router)
api.include_router(history.router)
api.include_router(settings.router)
