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

    # Session
    SESSION_DEFAULT_DAYS: int = 7
    SESSION_REMEMBER_ME_DAYS: int = 30

    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    FRONTEND_URL: str = "http://localhost:3000"

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

        A strong secret key is used as HMAC signing material for integrity checks.

        Generate a secure key with:
            python -c "import secrets; print(secrets.token_hex(64))"
        """
        if len(v) < 64:
            raise ValueError(
                "SECRET_KEY must be at least 64 characters long (≥ 512 bits). "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(64))\""
            )
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
