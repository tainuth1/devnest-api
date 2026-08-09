from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.audit import audit_logger, AuditEventType, AuditStatus
from app.shared import responses as res

AUTH_SIGNIN_LIMIT = "7/minute;30/hour"      # signin
AUTH_OTP_LIMIT = "3/10minute;10/hour"       # send OTP (register, forgot password)
AUTH_VERIFY_LIMIT = "7/minute;20/hour"      # verify OTP, password reset/update
AUTH_PROFILE_LIMIT = "10/minute;30/hour"    # update profile
AUTH_SESSION_LIMIT = "30/minute"            # signout, token refresh
AUTH_ME_LIMIT = "60/minute"                 # GET /me

limiter = Limiter(key_func=get_remote_address)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    ip = request.client.host if request.client else "unknown"
    audit_logger.log_event(
        event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
        status=AuditStatus.BLOCKED,
        client_ip=ip,
        details={
            "path": request.url.path,
            "method": request.method,
            "detail": str(exc.detail),
        },
    )

    response = res.error(message="Too many requests. Try again later.", status=429)
    if hasattr(request.app.state, "limiter") and hasattr(
        request.app.state.limiter, "_headers_resolver"
    ):
        try:
            response = request.app.state.limiter._headers_resolver(response, exc.stats)
        except Exception:
            pass
    return response