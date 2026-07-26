import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.logging_config import configure_logging
from app.middleware import AuthGateMiddleware, RequestLoggingMiddleware
from app.routers import build_api_router
from app.services.errors import DomainError

logger = logging.getLogger(__name__)

settings = get_settings()
configure_logging(settings)
settings.validate_runtime()
logger.info(
    "startup app_env=%s log_level=%s mailjet_configured=%s "
    "football_token_configured=%s auth_bypass=%s",
    settings.app_env,
    settings.log_level,
    settings.mailjet_configured,
    bool(settings.football_data_api_token.strip()),
    bool(settings.auth_bypass_email.strip()),
)

_docs = "/docs" if settings.is_development else None
_redoc = "/redoc" if settings.is_development else None
_openapi = "/openapi.json" if settings.is_development else None

app = FastAPI(
    title="Football Draft League API",
    version="0.1.0",
    docs_url=_docs,
    redoc_url=_redoc,
    openapi_url=_openapi,
)
origins = settings.cors_origin_list
if "*" in origins:
    raise RuntimeError("CORS_ORIGINS must not include '*' with allow_credentials=True")
# Last added runs outermost: CORS → access log → auth gate → app.
# Logging must wrap the auth gate so 401 short-circuits still get access logs.
app.add_middleware(AuthGateMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(build_api_router())


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    logger.warning(
        "DomainError status=%s path=%s detail=%s",
        exc.status_code,
        request.url.path,
        exc.message,
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    detail = str(exc.orig if getattr(exc, "orig", None) else exc)
    if len(detail) > 300:
        detail = detail[:299] + "…"
    logger.warning("IntegrityError path=%s detail=%s", request.url.path, detail)
    return JSONResponse(status_code=409, content={"detail": "Conflict: duplicate or invalid data"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
