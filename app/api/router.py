from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.user.router import router as user_admin_router
from app.modules.audit_log.router import router as audit_log_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(user_admin_router, prefix="/admin", tags=["Admin"])
api_router.include_router(audit_log_router, prefix="/admin/audit-logs", tags=["Audit Logs"])

