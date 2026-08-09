# Environment Configuration Guide

This document provides a comprehensive reference for configuring environment variables in the **FastAPI Authentication Boilerplate**.

Environment configuration is managed using **Pydantic Settings** (`pydantic-settings`), which loads variables from `.env` files or system environment variables, validates their types, and enforces security constraints upon application startup.

---

## Environment Variables Reference

Below is the complete list of environment variables categorized by functional component:

### 1. Application Settings

| Variable       | Type   | Default Value                          | Required | Description                                                                                         |
| :------------- | :----- | :------------------------------------- | :------- | :-------------------------------------------------------------------------------------------------- |
| `APP_NAME`     | `str`  | `"FastAPI Authentication Boilerplate"` | No       | Display name of the application.                                                                    |
| `APP_VERSION`  | `str`  | `"1.0.0"`                              | No       | API version shown in documentation (`/docs`, `/redoc`).                                             |
| `DEBUG`        | `bool` | `False`                                | No       | Enables OpenAPI docs (`/docs`, `/redoc`) and verbose debug logs. **Must be `False` in production.** |
| `APP_TIMEZONE` | `str`  | `"Asia/Phnom_Penh"`                    | No       | Timezone set on every PostgreSQL database session upon connection.                                  |

### 2. Database Settings

| Variable            | Type  | Default Value               | Required | Description                                                                                  |
| :------------------ | :---- | :-------------------------- | :------- | :------------------------------------------------------------------------------------------- |
| `DATABASE_URL`      | `str` | —                           | **Yes**  | Full PostgreSQL SQLAlchemy connection string (e.g. `postgresql://user:pass@db:5432/dbname`). |
| `POSTGRES_DB`       | `str` | `auth_boilerplate_db`       | Docker   | Database name consumed by Docker Compose `db` container.                                     |
| `POSTGRES_USER`     | `str` | `auth_boilerplate_user`     | Docker   | Database user consumed by Docker Compose `db` container.                                     |
| `POSTGRES_PASSWORD` | `str` | `auth_boilerplate_password` | Docker   | Database password consumed by Docker Compose `db` container.                                 |

### 3. Security & JWT Settings

| Variable                      | Type        | Default Value                                        | Required | Description                                                                      |
| :---------------------------- | :---------- | :--------------------------------------------------- | :------- | :------------------------------------------------------------------------------- |
| `SECRET_KEY`                  | `str`       | —                                                    | **Yes**  | 64-character (≥ 512-bit) secret key for JWT signing & HMAC integrity signatures. |
| `ALGORITHM`                   | `str`       | `"HS512"`                                            | No       | Cryptographic algorithm used for signing JWTs (`HS512`).                         |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `int`       | `15`                                                 | No       | Lifespan of short-lived JWT access tokens in minutes.                            |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | `int`       | `7`                                                  | No       | Lifespan of single-use refresh token HttpOnly cookies in days.                   |
| `CORS_ORIGINS`                | `list[str]` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | No       | JSON list of allowed origins for Cross-Origin Resource Sharing (CORS).           |

### 4. Email Delivery (Brevo REST API)

| Variable             | Type  | Default Value          | Required | Description                                                          |
| :------------------- | :---- | :--------------------- | :------- | :------------------------------------------------------------------- |
| `BREVO_API_KEY`      | `str` | `""`                   | Optional | API Key for Brevo (formerly Sendinblue) transactional email service. |
| `BREVO_SENDER_EMAIL` | `str` | `"noreply@domain.com"` | No       | Verified sender email address for outgoing transactional emails.     |
| `BREVO_SENDER_NAME`  | `str` | `"Your Name"`          | No       | Display name used in outgoing emails (e.g. OTP verification).        |

### 5. OTP & Account Lockout Settings

| Variable                    | Type  | Default Value | Required | Description                                                         |
| :-------------------------- | :---- | :------------ | :------- | :------------------------------------------------------------------ |
| `OTP_EXPIRE_MINUTES`        | `int` | `10`          | No       | Validity duration of email OTP verification codes in minutes.       |
| `OTP_MAX_ATTEMPTS`          | `int` | `5`           | No       | Maximum incorrect OTP entries allowed before invalidating code.     |
| `OTP_LENGTH`                | `int` | `6`           | No       | Length of generated numeric OTP codes.                              |
| `MAX_FAILED_LOGIN_ATTEMPTS` | `int` | `5`           | No       | Consecutive failed login attempts before temporary account lockout. |
| `ACCOUNT_LOCKOUT_MINUTES`   | `int` | `15`          | No       | Duration of temporary account lockout in minutes.                   |

### 6. Logging & Audit Settings

| Variable        | Type  | Default Value    | Required | Description                                                          |
| :-------------- | :---- | :--------------- | :------- | :------------------------------------------------------------------- |
| `LOG_LEVEL`     | `str` | `"INFO"`         | No       | Logging threshold (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `LOG_FORMAT`    | `str` | `"json"`         | No       | Log output format (`"json"` for structured logging or `"text"`).     |
| `LOG_FILE_PATH` | `str` | `""`             | No       | Optional file path for file logging (empty string disables file log writing). |

### 7. SSRF Protection Settings

| Variable                 | Type        | Default Value       | Required | Description                                                                          |
| :----------------------- | :---------- | :------------------ | :------- | :----------------------------------------------------------------------------------- |
| `SSRF_BLOCK_PRIVATE_IPS` | `bool`      | `True`              | No       | Enforce blocking of internal/private IP ranges (RFC 1918, loopback, cloud metadata). |
| `SSRF_ALLOWED_SCHEMES`   | `list[str]` | `["http", "https"]` | No       | Permitted URL protocols for outbound requests.                                       |
| `SSRF_ALLOWLIST_DOMAINS` | `list[str]` | `[]`                | No       | List of explicit domains allowed for outbound fetching.                              |
| `SSRF_MAX_REDIRECTS`     | `int`       | `3`                 | No       | Maximum HTTP redirects allowed during SSRF URL verification.                         |

---

## Generating a Secure `SECRET_KEY`

The application enforces **HS512** (HMAC-SHA512) signature verification, which requires a minimum key length of **64 characters** (512 bits of entropy). If `SECRET_KEY` has fewer than 64 characters, application startup will fail immediately.

Generate a 64-character secret key using any of the commands below:

### PowerShell (Windows)

```powershell
$rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
$bytes = New-Object byte[] 64
$rng.GetBytes($bytes)
[System.Convert]::ToBase64String($bytes)
```

### Python (Cross-platform)

```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

### OpenSSL (Linux / macOS)

```bash
openssl rand -hex 64
```

---

## Validation Schema (`app/core/config.py`)

The application validates all environment variables on boot via `app/core/config.py`.

```python
from pydantic import field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "FastAPI Authentication Boilerplate"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS512"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Timezone (applied to Postgres session on every connection)
    APP_TIMEZONE: str = "Asia/Phnom_Penh"

    # Email — Brevo REST API
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = "noreply@domain.com"
    BREVO_SENDER_NAME: str = "Your Name"

    # OTP
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    OTP_LENGTH: int = 6

    # Lockout
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # Logging & Audit
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" or "text"
    LOG_FILE_PATH: str = ""  # Empty string disables file log writing; audit logs are stored in PostgreSQL

    # SSRF Protection
    SSRF_BLOCK_PRIVATE_IPS: bool = True
    SSRF_ALLOWED_SCHEMES: list[str] = ["http", "https"]
    SSRF_ALLOWLIST_DOMAINS: list[str] = []
    SSRF_MAX_REDIRECTS: int = 3

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """
        Enforce a minimum SECRET_KEY length of 64 characters (≥ 512 bits).
        """
        if len(v) < 64:
            raise ValueError(
                "SECRET_KEY must be at least 64 characters long (≥ 512 bits for HS512)."
            )
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
```

### Key Validation Behaviors

1. **`DATABASE_URL` and `SECRET_KEY` are mandatory**: If either variable is missing from `.env` or system environment, FastAPI fails to start with a detailed validation error.
2. **`SECRET_KEY` Length Enforcement**: The `@field_validator("SECRET_KEY")` checks that `len(SECRET_KEY) >= 64`.
3. **Automatic Type Casting**: String values from `.env` are automatically parsed into Python types (`bool`, `int`, `list[str]`).
