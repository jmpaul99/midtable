from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.routers import build_api_router
from app.services.errors import DomainError

settings = get_settings()
settings.validate_runtime()

app = FastAPI(title="Football Draft League API", version="0.1.0")
origins = settings.cors_origin_list
if "*" in origins:
    raise RuntimeError("CORS_ORIGINS must not include '*' with allow_credentials=True")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(build_api_router())


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "Conflict: duplicate or invalid data"})


@app.get("/")
def root():
    return {"name": "football-draft-league", "docs": "/docs"}
