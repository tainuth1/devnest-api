import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded
from app.shared import responses as res

from app.core.config import settings
from app.core import timezone as tz
from app.core.logging import setup_logging
from app.core.middleware.correlation import CorrelationIdMiddleware
from app.core.audit import audit_logger, AuditEventType, AuditStatus
from app.core.limiter import limiter, rate_limit_exceeded_handler
from app.core.honeypot import HoneypotTriggered
from app.api.router import api_router
from app.database import Base, engine
import app.modules.auth.models  # noqa: F401 – register models before create_all
import app.core.honeypot  # noqa: F401 – register HoneypotEvent model before create_all
import app.modules.audit_log.models  # noqa: F401 – register AuditLog model before create_all

# Initialize structured logging
setup_logging()

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# Correlation & Request ID Middleware
app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With", "X-Request-ID"],
)



@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Prevent MIME-type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Block clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    # Modern OWASP standard: disable legacy browser XSS auditor (CSP is the authoritative protection)
    response.headers["X-XSS-Protection"] = "0"
    # Restrict Adobe Flash / PDF cross-domain policy loading
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    # Control referrer information leakage
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Disable unnecessary browser APIs
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # CSP: pure JSON API by default; allow Swagger UI / ReDoc CDN assets when in DEBUG mode
    if settings.DEBUG and request.url.path in ["/docs", "/redoc", "/openapi.json"]:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com;"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    # HSTS: only set over HTTPS (skip on localhost/debug to avoid breaking HTTP dev)
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    if "server" in response.headers:
        del response.headers["server"]
    if "Server" in response.headers:
        del response.headers["Server"]
    return response


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

logger = logging.getLogger("app.main")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Format request validation errors (Pydantic / FastAPI) into the
    StandardResponse envelope from app.shared.responses.
    """
    raw_errors = jsonable_encoder(exc.errors())
    sanitized_errors = []
    for err in raw_errors:
        if isinstance(err, dict):
            err.pop("input", None)
            sanitized_errors.append(err)
        else:
            sanitized_errors.append(err)

    message = "Validation error"
    if sanitized_errors:
        first_msg = sanitized_errors[0].get("msg", "")
        if first_msg.startswith("Value error, "):
            first_msg = first_msg[len("Value error, "):]
        if first_msg:
            message = first_msg

    return res.unprocessable(message=message, data=sanitized_errors)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Format HTTP exceptions (404, 405, 400, 401, 403, 409, etc.) into the
    StandardResponse envelope from app.shared.responses.
    """
    message = exc.detail if isinstance(exc.detail, str) else "An error occurred"
    data = exc.detail if not isinstance(exc.detail, str) else None
    return res.error(message=message, status=exc.status_code, data=data)


@app.exception_handler(HoneypotTriggered)
async def honeypot_triggered_handler(request: Request, exc: HoneypotTriggered) -> JSONResponse:
    """
    Silently absorbs honeypot triggers and returns a convincing fake 200 OK.
    The bot receives no error signal — it cannot tell its request was blocked.
    """
    return res.ok(message=exc.silent_message)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", str(exc), exc_info=exc)
    return res.server_error()


app.include_router(api_router, prefix="/api")


@app.get("/")
def root():
    if settings.DEBUG:
        return res.ok(
            message=f"Welcome to {settings.APP_NAME}",
            data={
                "version": settings.APP_VERSION,
                "debug": settings.DEBUG,
                "timezone": settings.APP_TIMEZONE,
                "current_time": tz.now().isoformat(),
            },
        )
    return res.ok(message=f"Welcome to {settings.APP_NAME}")

