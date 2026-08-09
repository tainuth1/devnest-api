# Honeypot & Threat Intelligence

This document details the automated honeypot bot-detection system, trap endpoints, threat intelligence logging, and silent rejection defense mechanisms implemented in `app/core/honeypot.py` for OWASP A07 (Identification and Authentication Failures).

---

## Honeypot Defense Architecture

The honeypot system detects automated malicious bots, web scrapers, and credential-stuffing tools without interfering with legitimate human users.

```text
[Client Request]
       │
       ▼
┌─────────────────────────────────────────┐
│ Honeypot Dependency Guard               │
│ (make_honeypot_guard / Pydantic Mixin) │
└─────────────────────────────────────────┘
       │
       ├─────────────────────────────────────────┐
       │ (Honeypot fields filled)                │ (Honeypot fields empty)
       ▼                                         ▼
┌─────────────────────────────────────────┐   ┌─────────────────────────────────────────┐
│ Bot Detected                            │   │ Legitimate Request                      │
│ 1. Log HoneypotEvent to DB              │   │ Pass through to Route Handler           │
│ 2. Log Audit Event (HONEYPOT_TRIGGERED) │   └─────────────────────────────────────────┘
│ 3. Raise HoneypotTriggered Exception    │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Global Exception Handler                │
│ Returns fake 200 OK (silent rejection) │
└─────────────────────────────────────────┘
```

---

## Hidden Trap Fields & Frontend Contract

Automated scripts and bots typically inspect form input names and populate every field in a JSON payload. The application injects hidden honeypot fields into authentication request payloads that real users never see or populate.

### 1. Honeypot Field Contract

The backend expects two invisible trap fields in incoming JSON request payloads:

```json
{
    "email": "user@example.com",
    "password": "Password123!",
    "website": "",
    "phone_confirm": ""
}
```

- `website` (`str`): Hidden trap field (default: `""`).
- `phone_confirm` (`str`): Hidden trap field (default: `""`).

### 2. Frontend HTML / CSS Implementation

In client interfaces, these fields are hidden using CSS and excluded from accessibility focus trees:

```html
<!-- Hidden from human users, visible to DOM crawlers and bots -->
<input
    type="text"
    name="website"
    value=""
    style="display:none"
    tabindex="-1"
    autocomplete="off"
/>
<input
    type="text"
    name="phone_confirm"
    value=""
    style="display:none"
    tabindex="-1"
    autocomplete="off"
/>
```

### 3. Pydantic `HoneypotMixin` (`app/core/honeypot.py`)

Request DTO schemas inherit from `HoneypotMixin`:

```python
class HoneypotMixin(BaseModel):
    website: str = Field(default="", exclude=True)
    phone_confirm: str = Field(default="", exclude=True)
```

By specifying `exclude=True`, Pydantic automatically strips `website` and `phone_confirm` from `model_dump()` output, preventing them from polluting internal service layers.

---

## Pre-Configured Endpoint Guards

The application enforces honeypot checks across authentication routes using pre-configured dependency guards:

| Endpoint                          | Guard Dependency            | Fake Response Message (Silent Rejection)                                  |
| :-------------------------------- | :-------------------------- | :------------------------------------------------------------------------ |
| `POST /api/auth/register`         | `honeypot_register`         | `"Account created successfully. Please check your email..."`              |
| `POST /api/auth/login`            | `honeypot_login`            | `"If your credentials are correct, you will be signed in."`               |
| `POST /api/auth/forgot-password`  | `honeypot_forgot_password`  | `"If that email address is registered, you will receive a reset link..."` |
| `POST /api/auth/verify-otp`       | `honeypot_verify_otp`       | `"OTP verified successfully."`                                            |
| `POST /api/auth/verify-reset-otp` | `honeypot_verify_reset_otp` | `"OTP verified successfully."`                                            |
| `POST /api/auth/reset-password`   | `honeypot_reset_password`   | `"Password reset successfully."`                                          |

---

## Silent Rejection Mechanism (`HoneypotTriggered`)

When a honeypot field contains a non-empty value, the guard dependency immediately logs the incident and raises a `HoneypotTriggered` custom exception.

```python
class HoneypotTriggered(Exception):
    def __init__(self, silent_message: str) -> None:
        self.silent_message = silent_message
        super().__init__(silent_message)
```

### Why Fake 200 OK?

In `app/main.py`, a dedicated exception handler catches `HoneypotTriggered`:

```python
@app.exception_handler(HoneypotTriggered)
async def honeypot_triggered_handler(request: Request, exc: HoneypotTriggered) -> JSONResponse:
    return res.ok(message=exc.silent_message)
```

1. **Deceives Automated Bots**: The bot receives a standard `200 OK` success envelope. It cannot tell that its request was intercepted and ignored.
2. **Prevents Adaptive Attack Logic**: Bots receive no error codes (`400`, `422`, `403`) to indicate that their payload format was flagged.
3. **Stalls Automated Retries**: Prevents bots from tuning payload parameter strategies or attempting bypass variations.

---

## Threat Intelligence & Event Logging (`HoneypotEvent`)

Every honeypot trap event is saved to the PostgreSQL `honeypot_events` database table and forwarded to the security audit logger (`audit_logger.log_event`).

### `HoneypotEvent` Table Schema (`app/core/honeypot.py`)

| Field Name      | Type           | Constraints         | Description                                                         |
| :-------------- | :------------- | :------------------ | :------------------------------------------------------------------ |
| `id`            | `UUID`         | Primary Key         | Unique honeypot incident identifier.                                |
| `ip_address`    | `String(45)`   | Index, Non-nullable | IPv4 or IPv6 address of the attacking client.                       |
| `user_agent`    | `String(512)`  | Nullable            | Raw User-Agent string for bot fingerprinting.                       |
| `endpoint`      | `String(100)`  | Index, Non-nullable | Targeted API endpoint path (e.g. `/auth/login`).                    |
| `filled_fields` | `String(255)`  | Non-nullable        | Comma-separated list of triggered trap fields (e.g. `"website"`).   |
| `body_snippet`  | `Text`         | Nullable            | Sanitized request body payload snippet (passwords/tokens redacted). |
| `created_at`    | `DateTime(tz)` | Non-nullable        | Incident timestamp.                                                 |

### Data Sanitization

Before saving `body_snippet` to PostgreSQL, sensitive payload keys (`password`, `new_password`, `otp`, `token`, `code`) are automatically redacted to `***` to preserve data privacy standards.
