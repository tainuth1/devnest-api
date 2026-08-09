# Architecture Overview

This document provides a high-level technical overview of the architecture, component structure, middleware pipeline, and response standard in the **FastAPI Authentication Boilerplate**.

---

## Modular Directory Architecture

The application adopts a modular, domain-driven directory structure designed for scalability, separation of concerns, and clean maintainability.

```text
app/
├── api/
│   └── router.py                 # Top-level API router aggregating all module sub-routers
├── core/
│   ├── audit.py                  # Database security audit logger & event tracker
│   ├── config.py                 # Pydantic Settings configuration & validation
│   ├── cookie.py                 # HttpOnly refresh token cookie helpers
│   ├── enums.py                  # Core system enums (UserRole, UserStatus, etc.)
│   ├── honeypot.py               # OWASP A07 honeypot trap endpoints & threat scoring
│   ├── integrity.py              # Cryptographic HMAC SHA-256 payload signing
│   ├── limiter.py                # Rate limiting setup & slowapi integration
│   ├── logging.py                # Structured JSON logging initialization
│   ├── middleware/
│   │   └── correlation.py        # Request Correlation ID tracking middleware
│   ├── otp.py                    # One-Time Password generation & verification
│   ├── password_security.py      # OWASP password complexity & breached password check
│   ├── sanitize.py               # Log input sanitization helpers
│   ├── security.py               # JWT generation & bcrypt password hashing
│   ├── ssrf.py                   # Server-Side Request Forgery validation engine
│   └── timezone.py               # Application timezone utilities
├── modules/
│   ├── audit_log/                # Audit Log feature module
│   │   ├── dependencies.py       # Audit log query dependencies
│   │   ├── models.py             # AuditLog SQLAlchemy ORM model
│   │   ├── router.py             # Audit log admin endpoints
│   │   ├── schemas.py            # Pydantic request/response schemas
│   │   └── service.py            # Audit log database querying service
│   ├── auth/                     # Authentication & Authorization feature module
│   │   ├── dependencies.py       # Auth dependencies (get_current_user, RequireRole)
│   │   ├── models.py             # User and RefreshToken ORM models
│   │   ├── router.py             # Authentication endpoints (/api/auth)
│   │   ├── schemas.py            # Auth request/response schemas
│   │   └── service.py            # Core authentication business logic & token rotation
│   └── user/                     # User Management feature module
│       ├── dependencies.py       # User lookup & authorization dependencies
│       ├── models.py             # User ORM model references
│       ├── router.py             # Admin user management endpoints (/api/admin)
│       ├── schemas.py            # User profile & management schemas
│       └── service.py            # User management service logic
├── shared/
│   └── responses.py              # Standardized API response envelope & helpers
├── database.py                   # SQLAlchemy engine, SessionLocal, Base model
└── main.py                       # Application entrypoint & FastAPI app factory
```

### Core Architecture Layers

1. **`app/core/`**: Infrastructure, security algorithms, cross-cutting configuration, and security middleware.
2. **`app/modules/`**: Autonomous domain feature packages. Each package contains its own models, schemas, service logic, dependencies, and API router.
3. **`app/api/`**: Central routing layer that aggregates module routers under versioned URL prefixes.
4. **`app/shared/`**: Common response utilities and generic helpers shared across all domain modules.

---

## Application Entrypoint & App Factory (`app/main.py`)

The application entrypoint `app/main.py` initializes structured logging, binds database ORM models, creates the FastAPI application instance, registers middleware, configures global exception handlers, and attaches top-level routers.

```python
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)
```

### Security via Conditional Docs

When `DEBUG=False` in production:

- Interactive OpenAPI Swagger UI (`/docs`) is disabled.
- ReDoc documentation (`/redoc`) is disabled.
- The raw OpenAPI specification JSON (`/openapi.json`) is disabled.

---

## Middleware Stack

Every incoming HTTP request traverses a multi-layered middleware stack in a strict execution order:

```text
[Incoming HTTP Request]
       │
       ▼
┌─────────────────────────────────────────┐
│ 1. CorrelationIdMiddleware              │  Assigns / extracts X-Request-ID header
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 2. CORSMiddleware                       │  Validates allowed origins, methods, headers
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 3. Security Headers Middleware          │  Injects OWASP security headers (CSP, HSTS, etc.)
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 4. Rate Limiting Middleware (Slowapi)   │  Evaluates client IP rate limits
└─────────────────────────────────────────┘
       │
       ▼
[Route Handler Execution]
```

### 1. Request Correlation ID (`CorrelationIdMiddleware`)

- Inspects incoming requests for an `X-Request-ID` or `X-Correlation-ID` header.
- If missing, generates a unique UUIDv4 correlation ID.
- Binds the correlation ID to the logging context and attaches it to the HTTP response headers as `X-Request-ID`.

### 2. CORS Policy (`CORSMiddleware`)

- Configured using `settings.CORS_ORIGINS`.
- Restricts cross-origin requests to trusted origins while allowing credentials (`allow_credentials=True`) for HttpOnly cookies.

### 3. OWASP Security Headers (`add_security_headers`)

Applied dynamically to every HTTP response:

- `X-Content-Type-Options: nosniff`: Prevents browsers from MIME-sniffing response types.
- `X-Frame-Options: DENY`: Prevents clickjacking by blocking iframe embedding.
- `X-XSS-Protection: 0`: Disables legacy browser XSS filtering in favor of CSP.
- `Referrer-Policy: strict-origin-when-cross-origin`: Restricts referrer data leakage.
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`: Disables unused browser APIs.
- `Content-Security-Policy`: Restricts content execution. In production, set to `default-src 'none'; frame-ancestors 'none'`.
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`: Enforces HTTPS in non-DEBUG mode.
- `Server`: Strip server headers to prevent technology stack fingerprinting.

### 4. Global Exception Handlers

The application captures all runtime exceptions and converts them into standardized JSON error responses:

- `RequestValidationError`: Formats Pydantic validation failures into a clean 422 Unprocessable Entity response with input fields sanitized.
- `StarletteHTTPException`: Converts standard HTTP errors (400, 401, 403, 404, 409) into standard JSON error envelopes.
- `HoneypotTriggered`: Silently absorbs honeypot trigger attempts and returns a fake 200 OK response to deceive bots.
- `RateLimitExceeded`: Catches rate limit violations and returns a 429 Too Many Requests response.
- `Exception` (Global Catch-all): Catches unhandled exceptions, logs full stack traces internally with correlation IDs, and returns a safe 500 Internal Server Error without leaking internal details.

---

## Standardized API Response Format (`app/shared/responses.py`)

All API endpoints return responses encapsulated in a consistent JSON envelope defined by `StandardResponse[T]`.

### Response Envelope Schema

```json
{
    "status": 200,
    "success": true,
    "message": "Operation completed successfully",
    "data": {}
}
```

- `status` (`int`): HTTP status code.
- `success` (`bool`): `true` for 2xx responses, `false` for 4xx and 5xx errors.
- `message` (`str`): Human-readable summary message.
- `data` (`Optional[T]`): Payload object, array, or `null`.

### Pydantic Envelope Definition

```python
class StandardResponse(BaseModel, Generic[T]):
    status: int
    success: bool
    message: str
    data: Optional[T] = None
```

### Standard Response Helpers (`app/shared/responses.py`)

#### Success Helpers

- `ok(message="Success", data=None)`: Returns 200 OK.
- `created(message="Created successfully", data=None)`: Returns 201 Created.
- `no_content(message="Deleted successfully")`: Returns 200 OK with `data: null`.

#### Error Helpers

- `bad_request(message="Bad request")`: Returns 400 Bad Request.
- `unauthorized(message="Unauthorized")`: Returns 401 Unauthorized.
- `forbidden(message="Forbidden")`: Returns 403 Forbidden.
- `not_found(message="Not found")`: Returns 404 Not Found.
- `conflict(message="Conflict")`: Returns 409 Conflict.
- `unprocessable(message="Unprocessable entity")`: Returns 422 Unprocessable Entity.
- `server_error(message="An unexpected error occurred.")`: Returns 500 Internal Server Error.
