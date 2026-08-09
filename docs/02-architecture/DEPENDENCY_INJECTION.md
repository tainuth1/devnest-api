# Dependency Injection

This document explains the Dependency Injection (DI) system and key security dependencies in the **FastAPI Authentication Boilerplate**.

---

## FastAPI Dependency Injection Overview

FastAPI provides a powerful, type-safe Dependency Injection framework using `Depends(...)`. Dependencies are reusable callables (functions or class instances) that FastAPI executes before invoking a route handler.

In this boilerplate, dependency injection is used for:

1. **Database Session Management**: Providing request-scoped SQLAlchemy sessions (`get_db`).
2. **Authentication & Identity**: Parsing, decoding, and validating JWT access tokens (`get_current_user`).
3. **Authorization & RBAC**: Enforcing server-side role checks (`require_role`, `require_admin`, `require_developer`).
4. **Rate Limiting Guard**: Enforcing per-IP request rates using `slowapi` (`limiter.limit(...)`).

---

## 1. Database Session Manager Dependency (`get_db`)

Located in `app/database.py`, `get_db` handles the lifecycle of PostgreSQL database connections for each incoming request.

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Execution Flow & Guarantees

1. **Acquisition**: A new SQLAlchemy `Session` instance is created via `SessionLocal()`.
2. **Yield**: FastAPI passes the active `db` session into route handlers declared with `db: Session = Depends(get_db)`.
3. **Cleanup**: Regardless of whether the route succeeds or throws an unhandled exception, the `finally` block executes `db.close()`, returning the connection back to the connection pool and preventing socket leaks.

#### Route Handler Example

```python
@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

---

## 2. JWT Authentication Dependency (`get_current_user`)

Located in `app/modules/auth/dependencies.py`, `get_current_user` extracts the JWT Bearer token from request headers, validates its cryptographic signature, checks user existence in PostgreSQL, and verifies account security state.

```python
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    ...
```

### Security Checks Performed

1. **Header Validation**: Checks for valid `Authorization: Bearer <token>` credentials. Raises `401 Unauthorized` if missing or malformed.
2. **Signature & Expiration**: Decodes the JWT using `decode_access_token(token)` with `HS512` algorithm. Raises `401 Unauthorized` if expired or invalid.
3. **User Existence**: Looks up the user by `sub` (UUID string) in PostgreSQL. Raises `401 Unauthorized` if the user no longer exists.
4. **Account Status Verification**: Checks `user.status`. If `INACTIVE`, `SUSPENDED`, or `BANNED`, logs a security audit event and raises `403 Forbidden`.
5. **Account Lockout Guard**: Evaluates `user.is_locked_out`. If the user is currently locked out due to multiple failed login attempts, raises `403 Forbidden`.

#### Route Handler Example

```python
@router.get("/api/auth/me")
def read_current_user(current_user: User = Depends(get_current_user)):
    return res.ok(data=UserResponse.model_validate(current_user))
```

---

## 3. RBAC Authorization Dependency (`require_role`)

Located in `app/modules/auth/rbac.py`, `require_role` provides a composable factory for Role-Based Access Control following OWASP A01 (Broken Access Control) guidelines.

```python
def require_role(*roles: UserRole):
    allowed = frozenset(roles)

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            audit_logger.log_event(
                event_type=AuditEventType.ACCESS_DENIED_UNAUTHORIZED,
                status=AuditStatus.BLOCKED,
                user_id=current_user.id,
                details={
                    "user_role": current_user.role.value,
                    "required_roles": [r.value for r in allowed],
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _check
```

### Pre-defined Convenience Aliases

For readable route definitions, `rbac.py` provides pre-configured role dependency shortcuts:

- `require_active_user`: Semantic alias for `get_current_user`.
- `require_admin`: Equivalent to `require_role(UserRole.ADMIN)`.
- `require_developer`: Equivalent to `require_role(UserRole.DEVELOPER)`.
- `require_admin_or_developer`: Equivalent to `require_role(UserRole.ADMIN, UserRole.DEVELOPER)`.

#### Route Handler Example

```python
from app.modules.auth.rbac import require_admin, require_role
from app.core.enums import UserRole

# Admin only endpoint
@router.get("/api/admin/users", dependencies=[Depends(require_admin)])
def get_all_users(db: Session = Depends(get_db)):
    ...

# Admin or Developer endpoint with injected User object
@router.delete("/api/admin/users/{user_id}")
def delete_user(
    user_id: uuid.UUID,
    admin_user: User = Depends(require_role(UserRole.ADMIN, UserRole.DEVELOPER)),
    db: Session = Depends(get_db),
):
    ...
```

---

## 4. Rate Limiting Dependency (`slowapi`)

Located in `app/core/limiter.py`, rate limiting is enforced per-IP using `slowapi`.

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Pre-defined Limit Constants
AUTH_SIGNIN_LIMIT = "7/minute;30/hour"
AUTH_OTP_LIMIT = "3/10minute;10/hour"
AUTH_VERIFY_LIMIT = "7/minute;20/hour"
AUTH_PROFILE_LIMIT = "10/minute;30/hour"
AUTH_SESSION_LIMIT = "30/minute"
AUTH_ME_LIMIT = "60/minute"
```

### Route Handler Example

```python
@router.post("/login")
@limiter.limit(AUTH_SIGNIN_LIMIT)
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    ...
```

> [!NOTE]
> Route handlers using `@limiter.limit(...)` must include `request: Request` as a parameter so `slowapi` can extract client IP details via `get_remote_address`. When rate limits are exceeded, `rate_limit_exceeded_handler` logs a security audit event and returns a standardized `429 Too Many Requests` JSON response.
