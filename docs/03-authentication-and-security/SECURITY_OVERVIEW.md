# Security Overview

This document provides a technical security overview of the defensive architecture, OWASP Top 10 compliance mapping, password security policies, anti-timing measures, and account lockout protections in the **FastAPI Authentication Boilerplate**.

---

## OWASP Top 10 (2021) Compliance Matrix

The boilerplate implements security controls aligned with the OWASP Top 10 guidelines:

| OWASP Standard | Risk Category                            | Boilerplate Implementation Details                                                                                                                                                       |
| :------------- | :--------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A01:2021**   | Broken Access Control                    | Server-side RBAC dependencies (`require_role`, `require_admin`) with deny-by-default execution. Mandatory JWT authorization on protected routes (`get_current_user`).                    |
| **A02:2021**   | Cryptographic Failures                   | Strong `HS512` JWT signing with 64-character (≥ 512-bit) `SECRET_KEY` validation on boot. Passwords hashed with `bcrypt` (cost 12). SHA-256 token hashing at rest for refresh tokens.    |
| **A03:2021**   | Injection                                | SQLAlchemy 2.0 ORM parameterized queries prevent SQL injection. Pydantic request body validation schemas sanitize inputs.                                                                |
| **A04:2021**   | Insecure Design                          | Dual-token authentication architecture (short-lived access tokens + single-use refresh tokens in HttpOnly cookies). CSPRNG for OTP generation. Rate limiting on all endpoints.           |
| **A05:2021**   | Security Misconfiguration                | Production hardening (`DEBUG=False` disables Swagger `/docs`, ReDoc `/redoc`, and OpenAPI JSON). Security headers (CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy). |
| **A06:2021**   | Vulnerable & Outdated Components         | Automated dependency vulnerability scanning with `pip-audit`, Dependabot updates, and pin-to-exact versions in CI/CD pipeline.                                                           |
| **A07:2021**   | Identification & Authentication Failures | Anti-timing dummy password verification. 15-minute account lockout after 5 failed login attempts. Breached password blocklist. Multi-phase OTP email verification. Honeypot defense.     |
| **A08:2021**   | Software & Data Integrity Failures       | Cryptographic HMAC SHA-256 payload signing (`app/core/integrity.py`) with constant-time verification (`hmac.compare_digest`) and mandatory JWT claim enforcement.                        |
| **A09:2021**   | Security Logging & Monitoring Failures   | Correlation ID tracing (`X-Request-ID`). Structured JSON logger. Database security audit logging (`app/core/audit.py`) tracking all auth events and threat alerts.                       |
| **A10:2021**   | Server-Side Request Forgery (SSRF)       | Outbound URL validation engine (`app/core/ssrf.py`) enforcing scheme allowlists, domain allowlists, and RFC 1918 / loopback / cloud metadata IP blocklists.                              |

---

## Password Security Policies & Breached Password Checks

Password strength validation is enforced in `app/core/password_security.py` using `validate_password_strength(...)`.

### 1. Complexity Requirements

- **Minimum Length**: Must be at least 8 characters long.
- **Uppercase Character**: Must contain at least one uppercase letter (`A-Z`).
- **Lowercase Character**: Must contain at least one lowercase letter (`a-z`).
- **Numeric Digit**: Must contain at least one digit (`0-9`).
- **Special Character**: Must contain at least one non-alphanumeric character (e.g. `!@#$%^&*`).

### 2. Common Breached Password Blocklist

The application filters incoming passwords against a blocklist of common, compromised passwords (`COMMON_BREACHED_PASSWORDS` set in `app/core/password_security.py`), including predictable strings like `password123`, `admin123!`, `welcome123!`, `12345678`, and `changeme123`. If matched, registration or password update is rejected.

### 3. Contextual User Detail Filtering

To prevent users from including personal identification details in their passwords:

- Passwords must not contain the `username` (if length ≥ 3).
- Passwords must not contain the local part of the `email` address (e.g. `john` from `john@example.com`).

```python
def validate_password_strength(password: str, username: str = "", email: str = "") -> str:
    ...
```

---

## Anti-Timing Attack Measures

In standard authentication implementations, an API might return a 401 response almost instantly when a targeted user email does not exist, but take 100-300ms to return a 401 when the user exists (due to the CPU-intensive `bcrypt` calculation). Attackers exploit this timing discrepancy to enumerate valid user accounts on a system.

### Dummy Hash Verification (`verify_dummy_password`)

Located in `app/core/security.py`, the system maintains a pre-computed dummy bcrypt hash:

```python
_DUMMY_BCRYPT_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"

def verify_dummy_password() -> bool:
    """
    Executes passlib bcrypt verification against a pre-computed dummy hash.
    Used when a target user is not found to ensure constant response times
    and prevent timing-based user enumeration attacks.
    """
    return _pwd_context.verify("DummyPassword123!", _DUMMY_BCRYPT_HASH)
```

During login (`AuthService.login`), if a target `login_id` (email or username) is not found in PostgreSQL, `verify_dummy_password()` is invoked prior to raising `401 Unauthorized`. This ensures the execution time for non-existent user login attempts matches the execution time for existent users.

---

## Account Lockout Protection

To defend against online brute-force credential stuffing and dictionary attacks, the application enforces automatic temporary account lockouts.

```python
# Settings in app/core/config.py
MAX_FAILED_LOGIN_ATTEMPTS = 5
ACCOUNT_LOCKOUT_MINUTES = 15
```

### Lockout Mechanism

1. **Attempt Tracking**: The `User` ORM model tracks `failed_login_attempts` (`Integer`) and `locked_until` (`DateTime(tz)`).
2. **Threshold Exceeded**: Upon the 5th consecutive invalid password entry, `user.locked_until` is set to `tz.now() + timedelta(minutes=15)` and an `AUTH_LOCKOUT_TRIGGERED` audit event is logged.
3. **Lockout Enforcement**: During login, `user.is_locked_out` checks if `locked_until` is in the future. If active, authentication is blocked immediately with a `401 Unauthorized` response indicating remaining lockout minutes.
4. **Automatic Reset**: When the 15-minute lockout period expires, or upon a successful login after the lockout period, `failed_login_attempts` is reset to `0` and `locked_until` is cleared.
