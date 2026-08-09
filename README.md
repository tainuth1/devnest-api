# FastAPI Authentication Boilerplate

A production-ready FastAPI boilerplate for JWT-based authentication with PostgreSQL, Role-Based Access Control (RBAC), rate limiting, threat intelligence, and Docker Compose orchestration, built following OWASP Top 10 security best practices.

![FastAPI Swagger UI](assets/Swegger%20UI%20Endpoint.png)

---

## Technical Features & Security Controls

### Core Authentication & Session Management

- **HS512 JWT Access Tokens**: Signed with HMAC-SHA512 using a mandatory 64-character (≥ 512-bit) secret key.
- **HttpOnly Refresh Cookies**: Long-lived refresh tokens stored exclusively in secure `HttpOnly`, `SameSite=Lax` cookies.
- **Single-Use Refresh Token Rotation**: Automatic token renewal on refresh. Reusing a previously rotated refresh token triggers an immediate security alert and revokes all active sessions for the user.
- **Two-Phase Registration & Recovery**: Email OTP verification for account activation and password resets powered by Brevo REST API.

### Security Hardening & Threat Protection

- **Role-Based Access Control (RBAC)**: Server-side role enforcement dependencies (`require_role`, `require_admin`, `require_developer`) with deny-by-default execution.
- **Anti-Timing Attack Protection**: Constant-time dummy password verification (`verify_dummy_password`) for non-existent users during login.
- **Account Lockout Guard**: Temporary 15-minute account lockout after 5 consecutive failed login attempts.
- **Breached Password Blocklist**: Rejects top common breached passwords and contextual username/email details.
- **Honeypot Bot Trap Detection**: Invisible trap fields in payloads detect automated bots and return fake 200 OK responses to confuse scrapers.
- **HMAC SHA-256 Payload Signing**: Cryptographic payload signing with constant-time signature comparison (`hmac.compare_digest`).
- **Structured Audit Logging & Correlation ID**: Request-scoped `X-Request-ID` tracing, sensitive credential redaction, and PostgreSQL security audit event tracking (`audit_logs`).
- **SSRF Validation Engine**: Outbound URL parsing, DNS resolution checks, and private IP blocklists (RFC 1918, loopback, cloud metadata IPs).

---

## Tech Stack

| Component            | Technology               | Version / Standard   |
| :------------------- | :----------------------- | :------------------- |
| **Framework**        | FastAPI                  | `0.111.0+`           |
| **Language**         | Python                   | `3.11+`              |
| **Database**         | PostgreSQL               | `16-alpine`          |
| **ORM & Migrations** | SQLAlchemy 2.0 & Alembic | `2.0+`               |
| **Authentication**   | PyJWT                    | `HS512`              |
| **Password Hashing** | Passlib & Bcrypt         | `cost 12`            |
| **Rate Limiting**    | Slowapi                  | `get_remote_address` |
| **Containerization** | Docker & Docker Compose  | `v2.0+`              |

---

## Quickstart Guide

### 1. Clone & Configure Environment

```bash
git clone https://github.com/your-username/fastapi-authentication-boilerplate.git
cd fastapi-authentication-boilerplate
cp .env.example .env
```

### 2. Generate a Secure `SECRET_KEY`

Generating a 64-character (≥ 512-bit) secret key is mandatory before starting the application:

```bash
# Cross-platform Python
python -c "import secrets; print(secrets.token_hex(64))"

# Linux / macOS OpenSSL
openssl rand -hex 64
```

Copy the generated output to `SECRET_KEY=` in your `.env` file.

### 3. Run with Docker Compose

#### Development Mode (Hot-Reloading & Auto-Migrations)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

#### Production Mode (Multi-Worker Execution)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Access the interactive API documentation at:

- **Swagger UI**: `http://localhost:8000/docs` (DEBUG mode only)
- **ReDoc**: `http://localhost:8000/redoc` (DEBUG mode only)

---

## Pre-Seeded Default Accounts

On initial container launch, database migrations (`alembic upgrade head`) and user seeding (`scripts/seed_users.py`) execute automatically.

| Role          | Username            | Default Email           | Default Password       |
| :------------ | :------------------ | :---------------------- | :--------------------- |
| **User**      | `default_user`      | `user@example.com`      | `UserDefault123!`      |
| **Admin**     | `default_admin`     | `admin@example.com`     | `AdminDefault123!`     |
| **Developer** | `default_developer` | `developer@example.com` | `DeveloperDefault123!` |

> Credentials can be customized in `.env` using `SEED_USER_*`, `SEED_ADMIN_*`, and `SEED_DEV_*` override variables.

---

## API Endpoints Summary

| Method        | Path                                | Description                                             | Access Level      |
| :------------ | :---------------------------------- | :------------------------------------------------------ | :---------------- |
| `POST`        | `/api/auth/register`                | Register account (Phase 1: OTP sent to email)           | Public            |
| `POST`        | `/api/auth/verify-otp`              | Verify OTP code & activate account (Phase 2)            | Public            |
| `POST`        | `/api/auth/login`                   | Authenticate & set HttpOnly refresh cookie              | Public            |
| `POST`        | `/api/auth/refresh`                 | Rotate refresh token & issue new access token           | Refresh Cookie    |
| `POST`        | `/api/auth/logout`                  | Revoke refresh token & clear cookie                     | Refresh Cookie    |
| `GET`         | `/api/auth/me`                      | Get authenticated user profile                          | Bearer Token      |
| `PUT`/`PATCH` | `/api/auth/me`                      | Update authenticated user profile                       | Bearer Token      |
| `POST`        | `/api/auth/forgot-password`         | Request password reset OTP code                         | Public            |
| `POST`        | `/api/auth/verify-reset-otp`        | Verify password reset OTP code                          | Public            |
| `POST`        | `/api/auth/reset-password`          | Reset password with verified OTP                        | Public            |
| `POST`        | `/api/auth/change-password`         | Change password & revoke all sessions                   | Bearer Token      |
| `GET`         | `/api/admin/users`                  | List all registered users (paginated)                   | Admin             |
| `GET`         | `/api/admin/users/{user_id}`        | Get user details by UUID                                | Admin             |
| `PATCH`       | `/api/admin/users/{user_id}/status` | Update account status (`active`, `suspended`, `banned`) | Admin             |
| `GET`         | `/api/admin/system/info`            | Get system status & user metrics                        | Admin / Developer |
| `GET`         | `/api/admin/audit-logs`             | Query & filter database security audit logs             | Admin / Developer |

---

## Complete Project Documentation

Detailed technical documentation is available under `docs/`:

### 01. Getting Started

- [Quickstart Guide](docs/01-getting-started/QUICKSTART.md) — Local venv & Docker Compose environment setup.
- [Environment Configuration Guide](docs/01-getting-started/CONFIGURATION.md) — Full `.env` variable reference & Pydantic validation schema.
- [User Roles & Database Seeding Guide](docs/01-getting-started/SEEDING_AND_ROLES.md) — RBAC access hierarchy and seeder script instructions.

### 02. Architecture

- [Architecture Overview](docs/02-architecture/ARCHITECTURE_OVERVIEW.md) — Directory layout, FastAPI entrypoint, and middleware stack.
- [Database & Migrations](docs/02-architecture/DATABASE_AND_MIGRATIONS.md) — SQLAlchemy 2.0 ORM schemas and Alembic migration lifecycle.
- [Dependency Injection](docs/02-architecture/DEPENDENCY_INJECTION.md) — Session management, auth dependencies, and rate limit guards.

### 03. Authentication & Security

- [Authentication Flows](docs/03-authentication-and-security/AUTHENTICATION_FLOWS.md) — Registration, login, token rotation, and password recovery workflows.
- [Security Overview](docs/03-authentication-and-security/SECURITY_OVERVIEW.md) — Security matrix, breached password filtering, and anti-timing controls.
- [Honeypot & Threat Intelligence](docs/03-authentication-and-security/HONEYPOT_AND_THREAT_INTEL.md) — Bot trap fields, silent rejection, and threat logging.
- [Data Integrity & HMAC Payload Signing](docs/03-authentication-and-security/DATA_INTEGRITY_HMAC.md) — Tamper-evident signing and constant-time verification.
- [Audit Logging & Security Monitoring](docs/03-authentication-and-security/AUDIT_LOGGING_AND_MONITORING.md) — Correlation ID tracing and JSON log redactors.
- [Server-Side Request Forgery Protection](docs/03-authentication-and-security/SSRF_PROTECTION.md) — URL validation engine and IP blocklists.

### 04. API Reference

- [Authentication API Reference](docs/04-api-reference/AUTH_API.md) — Complete endpoint reference for `/api/auth`.
- [User Management API Reference](docs/04-api-reference/USER_MANAGEMENT_API.md) — Admin user administration endpoints `/api/admin`.
- [Security Audit Log API Reference](docs/04-api-reference/AUDIT_LOG_API.md) — Audit log query API specs `/api/admin/audit-logs`.

---

## Directory Structure

```text
fastapi-authentication-boilerplate/
├── app/
│   ├── api/
│   │   └── router.py                 # Central API router aggregator
│   ├── core/
│   │   ├── audit.py                  # Database security audit logger & event tracker
│   │   ├── config.py                 # Pydantic Settings configuration & validation
│   │   ├── cookie.py                 # HttpOnly refresh token cookie helpers
│   │   ├── enums.py                  # Core system enums (UserRole, UserStatus)
│   │   ├── honeypot.py               # Honeypot trap endpoints & threat scoring
│   │   ├── integrity.py              # Cryptographic HMAC SHA-256 payload signing
│   │   ├── limiter.py                # Rate limiting setup & slowapi integration
│   │   ├── logging.py                # Structured JSON logging initialization
│   │   ├── middleware/
│   │   │   └── correlation.py        # Request Correlation ID tracking middleware
│   │   ├── otp.py                    # One-Time Password generation & verification
│   │   ├── password_security.py      # Password complexity & breached password check
│   │   ├── security.py               # JWT generation & bcrypt password hashing
│   │   └── ssrf.py                   # Server-Side Request Forgery validation engine
│   ├── modules/
│   │   ├── audit_log/                # Audit log feature module (models, service, router)
│   │   ├── auth/                     # Auth feature module (token rotation, OTP, service)
│   │   └── user/                     # User admin feature module (models, service, router)
│   ├── shared/
│   │   └── responses.py              # Standardized API response envelope & helpers
│   ├── database.py                   # SQLAlchemy engine, SessionLocal, Base model
│   └── main.py                       # FastAPI application entrypoint
├── assets/
│   └── Swegger UI Endpoint.png       # API documentation preview image
├── docs/                             # Project documentation suite (12 guides)
├── scripts/
│   ├── audit_dependencies.py         # Dependency vulnerability scanner
│   └── seed_users.py                 # Database user seeder script
├── docker-compose.yml                # Base Docker Compose configuration
├── docker-compose.dev.yml            # Development Docker Compose configuration (hot-reload)
├── docker-compose.prod.yml           # Production Docker Compose configuration (multi-worker)
└── requirements.txt                  # Python dependencies manifest
```

---

## License

This project is open-source and available under the [MIT License](LICENSE).
