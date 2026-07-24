from fastapi import APIRouter

from app.routers import (
    admin,
    analytics,
    auth_me,
    draft,
    health,
    internal,
    leagues,
    rankings,
    sync,
    templates,
)


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(auth_me.router)
    router.include_router(leagues.router)
    router.include_router(draft.router)
    router.include_router(sync.router)
    router.include_router(admin.router)
    router.include_router(templates.router)
    router.include_router(rankings.router)
    router.include_router(analytics.router)
    router.include_router(internal.router)
    return router
