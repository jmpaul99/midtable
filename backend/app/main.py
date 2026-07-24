from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
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

settings = get_settings()

app = FastAPI(title="Football Draft League API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth_me.router)
app.include_router(leagues.router)
app.include_router(draft.router)
app.include_router(sync.router)
app.include_router(admin.router)
app.include_router(templates.router)
app.include_router(rankings.router)
app.include_router(analytics.router)
app.include_router(internal.router)


@app.get("/")
def root():
    return {"name": "football-draft-league", "docs": "/docs"}
