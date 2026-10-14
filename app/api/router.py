from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.user.router import router as user_admin_router
from app.modules.audit_log.router import router as audit_log_router
from app.modules.projects.router import router as projects_router
from app.modules.collaborators.router import (
    project_collaborators_router,
    invitations_router,
)
from app.modules.notifications.router import router as notifications_router
from app.modules.flow.router import router as flow_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(user_admin_router, prefix="/admin", tags=["Admin"])
api_router.include_router(audit_log_router, prefix="/admin/audit-logs", tags=["Audit Logs"])
api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])
api_router.include_router(project_collaborators_router, prefix="/projects", tags=["Collaborators"])
api_router.include_router(invitations_router, prefix="/invitations", tags=["Invitations"])
api_router.include_router(flow_router, prefix="/projects", tags=["Flow Diagrams"])


