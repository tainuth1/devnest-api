# Database & Migrations

This document details the database architecture, connection pool management, SQLAlchemy 2.0 ORM data models, and Alembic database migration lifecycle in the **FastAPI Authentication Boilerplate**.

---

## Database Engine & Session Management (`app/database.py`)

The application uses **SQLAlchemy 2.0** with PostgreSQL as its primary database.

```python
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

is_sqlite = "sqlite" in settings.DATABASE_URL
engine_kwargs = {
    "pool_pre_ping": True,
    "connect_args": {"check_same_thread": False} if is_sqlite else {},
}
if not is_sqlite:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

if settings.DATABASE_URL and "sqlite" not in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_connection_timezone(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET TIME ZONE %s", (settings.APP_TIMEZONE,))
        finally:
            cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Key Connection Pool Features

1. **Connection Health (`pool_pre_ping=True`)**: Emits a lightweight `SELECT 1` ping before handing a connection from the pool to a request thread, preventing stale socket errors.
2. **Pool Sizing (`pool_size=10`, `max_overflow=20`)**: Manages up to 10 persistent database connections with 20 temporary overflow connections under heavy load.
3. **Automatic Timezone Enforcement**: Listeners issue `SET TIME ZONE` on every new connection so all SQL queries execute under the specified application timezone (`settings.APP_TIMEZONE`).
4. **Session Lifecycle Dependency (`get_db`)**: A FastAPI context manager dependency that yields a database session for each request and guarantees connection closure (`db.close()`) in a `finally` block upon request completion.

---

## SQLAlchemy 2.0 ORM Models Breakdown

The boilerplate leverages modern SQLAlchemy 2.0 type-annotated Mapped types (`Mapped[...]`, `mapped_column(...)`).

### 1. `User` Model (`app/modules/auth/models.py`)

Represents registered user accounts, credential storage, account security metrics, and role status.

```text
Table Name: users
Primary Key: id (UUID v4)
```

| Field Name              | Type               | Constraints                           | Description                                                   |
| :---------------------- | :----------------- | :------------------------------------ | :------------------------------------------------------------ |
| `id`                    | `UUID`             | Primary Key, Index                    | Unique UUIDv4 identifier.                                     |
| `email`                 | `String(255)`      | Unique, Index, Non-nullable           | Normalized email address.                                     |
| `username`              | `String(50)`       | Unique, Index, Nullable               | Optional unique display username.                             |
| `first_name`            | `String(100)`      | Nullable                              | User's first name.                                            |
| `last_name`             | `String(100)`      | Nullable                              | User's last name.                                             |
| `password`              | `String(255)`      | Non-nullable                          | `bcrypt` hashed password string.                              |
| `role`                  | `Enum(UserRole)`   | Default: `USER`, Non-nullable         | User role (`user`, `admin`, `developer`).                     |
| `status`                | `Enum(UserStatus)` | Default: `ACTIVE`, Non-nullable       | Account status (`active`, `inactive`, `suspended`, `banned`). |
| `created_at`            | `DateTime(tz)`     | Default: `tz.now`, Non-nullable       | Timestamp when user was created.                              |
| `updated_at`            | `DateTime(tz)`     | Default: `tz.now`, Onupdate: `tz.now` | Timestamp when user was last modified.                        |
| `last_login_at`         | `DateTime(tz)`     | Nullable                              | Timestamp of last successful authentication.                  |
| `failed_login_attempts` | `Integer`          | Default: `0`, Non-nullable            | Consecutive failed login counter.                             |
| `locked_until`          | `DateTime(tz)`     | Nullable                              | Expiration timestamp for temporary lockout guard.             |

#### Relationships & Properties

- `refresh_tokens`: One-to-many relationship with `RefreshToken` (`cascade="all, delete-orphan"`).
- `full_name`: Computed property returning first and last name or email fallback.
- `is_locked_out`: Evaluates if `locked_until` timestamp is in the future.

---

### 2. `RefreshToken` Model (`app/modules/auth/models.py`)

Manages single-use refresh token sessions for JWT rotation and token revocation.

```text
Table Name: refresh_tokens
Primary Key: id (UUID v4)
Foreign Key: user_id -> users.id (ON DELETE CASCADE)
```

| Field Name   | Type           | Constraints                     | Description                                       |
| :----------- | :------------- | :------------------------------ | :------------------------------------------------ |
| `id`         | `UUID`         | Primary Key                     | Unique token ID.                                  |
| `token`      | `String(512)`  | Unique, Index, Non-nullable     | Cryptographic refresh token payload.              |
| `user_id`    | `UUID`         | Foreign Key (`users.id`), Index | User reference (cascade deleted on user removal). |
| `expires_at` | `DateTime(tz)` | Non-nullable                    | Token expiration timestamp.                       |
| `revoked`    | `Boolean`      | Default: `False`, Non-nullable  | Revocation flag set upon rotation or logout.      |
| `created_at` | `DateTime(tz)` | Default: `tz.now`, Non-nullable | Token issuance timestamp.                         |

#### Relationships & Properties

- `user`: Many-to-one relationship back to `User`.
- `is_expired`: Evaluates if `expires_at` has passed.
- `is_valid`: Returns `True` if not revoked and not expired.

---

### 3. `AuditLog` Model (`app/modules/audit_log/models.py`)

Stores immutable security audit events for system operations and security incidents.

```text
Table Name: audit_logs
Primary Key: id (UUID v4)
Foreign Key: user_id -> users.id (ON DELETE SET NULL)
```

| Field Name   | Type           | Constraints                               | Description                                                 |
| :----------- | :------------- | :---------------------------------------- | :---------------------------------------------------------- |
| `id`         | `UUID`         | Primary Key                               | Unique log entry ID.                                        |
| `event_type` | `String(100)`  | Index, Non-nullable                       | Category (e.g. `AUTH_LOGIN_SUCCESS`, `HONEYPOT_TRIGGERED`). |
| `status`     | `String(50)`   | Index, Non-nullable                       | Event outcome (`SUCCESS`, `FAILURE`, `BLOCKED`, `ALERT`).   |
| `user_id`    | `UUID`         | Foreign Key (`users.id`), Index, Nullable | Associated user ID (retained as `NULL` if user is deleted). |
| `client_ip`  | `String(45)`   | Index, Nullable                           | IPv4 or IPv6 address of caller.                             |
| `user_agent` | `String(512)`  | Nullable                                  | Client HTTP User-Agent header string.                       |
| `request_id` | `String(100)`  | Index, Nullable                           | Request correlation ID for trace log matching.              |
| `details`    | `JSON`         | Nullable                                  | Sanitized event metadata payload (JSON).                    |
| `created_at` | `DateTime(tz)` | Index, Non-nullable                       | Event timestamp.                                            |

---

### 4. OTP Models & Security Design (`app/core/otp.py` & `app/modules/auth/models.py`)

One-Time Passwords (OTPs) are used for email registration verification and password resets.

```text
Table Names: pending_registrations, password_resets
```

#### Security Architecture

1. **CSPRNG Generation**: OTP numbers are generated via `secrets.randbelow` to guarantee cryptographic randomness.
2. **Bcrypt Hashing**: OTP codes are **never stored as plain text**. They are hashed using a dedicated `passlib` `bcrypt` context (`hash_otp(otp)`).
3. **Attempt & Expiry Limits**: Enforces 10-minute expiration and a 5-attempt limit per OTP to prevent brute-forcing.

#### `PendingRegistration` Schema

- Stores unverified registration attempts with `username`, `email`, `hashed_password`, `otp_hash`, `expires_at`, and `attempts`.

#### `PasswordReset` Schema

- Stores password reset requests with `email`, `otp_hash`, `expires_at`, and `attempts`.

---

## Alembic Migration Lifecycle

Database schema changes are managed declaratively using Alembic.

### 1. Generating a New Migration Revision

When ORM models in `app/modules/*/models.py` are created or updated, generate an autogenerated migration script:

```bash
alembic revision --autogenerate -m "add_new_feature_table"
```

Alembic inspects `Base.metadata` (configured in `alembic/env.py`) against the target PostgreSQL database schema and creates a new version script under `alembic/versions/`.

### 2. Applying Migrations (`upgrade`)

To apply pending migrations to the database schema:

```bash
# Upgrade database to the latest revision
alembic upgrade head

# Upgrade by a specific number of steps
alembic upgrade +1
```

### 3. Rolling Back Migrations (`downgrade`)

To revert applied schema migrations:

```bash
# Roll back the most recent migration step
alembic downgrade -1

# Roll back to base empty database
alembic downgrade base
```

### 4. Migration Execution in Docker

When running under Docker, `docker-entrypoint.sh` executes migrations automatically on container launch:

```bash
#!/bin/sh
set -e
echo "Running database migrations..."
alembic upgrade head
echo "Seeding default users..."
python scripts/seed_users.py
exec "$@"
```
