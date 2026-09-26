# Authentication API Reference

This document provides a technical specification for all endpoints under `/api/auth` in the **FastAPI Authentication Boilerplate**.

Base Path: `/api/auth`

---

## Endpoint Summary

| Method        | Path                         | Summary                              | Auth Required    | Rate Limit     |
| :------------ | :--------------------------- | :----------------------------------- | :--------------- | :------------- |
| `POST`        | `/api/auth/register`         | Phase 1: Register account & send OTP | No               | 3/10min, 10/hr |
| `POST`        | `/api/auth/verify-otp`       | Phase 2: Verify registration OTP     | No               | 7/min, 20/hr   |
| `POST`        | `/api/auth/login`            | Authenticate & create session cookie | No               | 7/min, 30/hr   |
| `POST`        | `/api/auth/logout`           | Revoke session & clear cookie        | Session Cookie   | 30/min         |
| `GET`         | `/api/auth/me`               | Get current user profile             | Session Cookie   | 60/min         |
| `PUT`/`PATCH` | `/api/auth/me`               | Update current user profile          | Session Cookie   | 10/min, 30/hr  |
| `POST`        | `/api/auth/forgot-password`  | Phase 1: Request password reset OTP  | No               | 3/10min, 10/hr |
| `POST`        | `/api/auth/verify-reset-otp` | Phase 2: Verify reset OTP code       | No               | 7/min, 20/hr   |
| `POST`        | `/api/auth/reset-password`   | Phase 3: Reset password with OTP     | No               | 7/min, 20/hr   |
| `POST`        | `/api/auth/change-password`  | Change password for active account   | Session Cookie   | 10/min, 30/hr  |

---

## Authentication Model

All protected endpoints authenticate via an **`HttpOnly` session cookie** (`session_id`) set automatically at login. No `Authorization` header or Bearer token is required or accepted.

| Cookie      | Value              | Lifetime         |
| :---------- | :----------------- | :--------------- |
| `session_id`| Raw session token  | 7 days (default) or 30 days (`remember_me=true`) |

The raw token is **never stored in the database** — only its SHA-256 hash is persisted in the `user_sessions` table. A session can be revoked at any time (logout, password change, admin status change).

---

## 1. `POST /api/auth/register`

Phase 1 of account creation. Validates input and dispatches a 6-digit OTP code to the provided email.

### Request Headers

```http
Content-Type: application/json
```

### Request Body Schema (`RegisterRequest`)

```json
{
    "username": "johndoe",
    "email": "john@example.com",
    "password": "Password123!",
    "website": "",
    "phone_confirm": ""
}
```

- `username` (`str`, required): 3–50 characters, letters/digits/underscores only.
- `email` (`str`, required): Valid email address.
- `password` (`str`, required): Min 8 chars, uppercase, lowercase, digit, special char.
- `website` & `phone_confirm` (`str`, optional): Invisible honeypot trap fields. Must be empty.

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "A verification code has been sent to john@example.com...",
    "data": {
        "email": "john@example.com"
    }
}
```

### cURL Example

```bash
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe",
    "email": "john@example.com",
    "password": "Password123!"
  }'
```

---

## 2. `POST /api/auth/verify-otp`

Phase 2 of account creation. Verifies the 6-digit email OTP and activates the user account in PostgreSQL.

### Request Body Schema (`VerifyOtpRequest`)

```json
{
    "email": "john@example.com",
    "otp_code": "042819",
    "website": "",
    "phone_confirm": ""
}
```

### Response (201 Created)

```json
{
    "status": 201,
    "success": true,
    "message": "Account created successfully. You can now sign in.",
    "data": {
        "email": "john@example.com",
        "username": "johndoe"
    }
}
```

### cURL Example

```bash
curl -X POST "http://localhost:8000/api/auth/verify-otp" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "otp_code": "042819"
  }'
```

---

## 3. `POST /api/auth/login`

Authenticates user credentials and creates a server-side session. Sets an `HttpOnly` `session_id` cookie that authenticates all subsequent requests.

### Request Body Schema (`LoginRequest`)

```json
{
    "login_id": "john@example.com",
    "password": "Password123!",
    "remember_me": false,
    "website": "",
    "phone_confirm": ""
}
```

- `login_id` (`str`): User's email or username.
- `remember_me` (`bool`, optional, default `false`): If `true`, session lasts **30 days**; otherwise **7 days**.

### Response Headers

```http
Set-Cookie: session_id=<token>; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "Login successful.",
    "data": {
        "user": {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "email": "john@example.com",
            "username": "johndoe",
            "role": "user",
            "status": "active",
            "first_name": "John",
            "last_name": "Doe"
        }
    }
}
```

### cURL Example

```bash
# Default session (7 days)
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{
    "login_id": "john@example.com",
    "password": "Password123!"
  }'

# Extended session (30 days — remember me)
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{
    "login_id": "john@example.com",
    "password": "Password123!",
    "remember_me": true
  }'
```

---

## 4. `POST /api/auth/logout`

Revokes the active server-side session in PostgreSQL and clears the `HttpOnly` session cookie.

### Request Headers

```http
Cookie: session_id=<token>
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "Logged out successfully.",
    "data": null
}
```

### cURL Example

```bash
curl -X POST "http://localhost:8000/api/auth/logout" \
  -b cookies.txt \
  -c cookies.txt
```

---

## 5. `GET /api/auth/me`

Fetches the profile details of the currently authenticated user. Requires a valid `session_id` cookie.

### Request Headers

```http
Cookie: session_id=<token>
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "User profile retrieved successfully.",
    "data": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "email": "john@example.com",
        "username": "johndoe",
        "role": "user",
        "status": "active",
        "first_name": "John",
        "last_name": "Doe",
        "created_at": "2026-08-09T10:00:00+00:00",
        "updated_at": "2026-08-09T10:00:00+00:00",
        "last_login_at": "2026-08-09T11:00:00+00:00"
    }
}
```

### cURL Example

```bash
curl -X GET "http://localhost:8000/api/auth/me" \
  -b cookies.txt
```

---

## 6. `PUT` / `PATCH /api/auth/me`

Updates profile details for the authenticated user.

### Request Headers

```http
Cookie: session_id=<token>
Content-Type: application/json
```

### Request Body Schema (`UpdateProfileRequest`)

```json
{
    "first_name": "Johnny",
    "last_name": "Doe",
    "username": "johnny_d"
}
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "User profile updated successfully.",
    "data": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "email": "john@example.com",
        "username": "johnny_d",
        "role": "user",
        "status": "active",
        "first_name": "Johnny",
        "last_name": "Doe",
        "created_at": "2026-08-09T10:00:00+00:00",
        "updated_at": "2026-08-09T11:30:00+00:00",
        "last_login_at": "2026-08-09T11:00:00+00:00"
    }
}
```

---

## 7. `POST /api/auth/forgot-password`

Phase 1 of password recovery. Requests a 6-digit OTP code sent to the user's email.

### Request Body Schema (`ForgotPasswordRequest`)

```json
{
    "email": "john@example.com",
    "website": "",
    "phone_confirm": ""
}
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "If that email address is registered, you will receive a password reset verification code shortly.",
    "data": {
        "email": "john@example.com"
    }
}
```

---

## 8. `POST /api/auth/verify-reset-otp`

Phase 2 of password recovery. Verifies that the password reset 6-digit OTP is valid.

### Request Body Schema (`VerifyResetOtpRequest`)

```json
{
    "email": "john@example.com",
    "otp_code": "042819",
    "website": "",
    "phone_confirm": ""
}
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "OTP code verified successfully. You can now set a new password.",
    "data": {
        "email": "john@example.com"
    }
}
```

---

## 9. `POST /api/auth/reset-password`

Phase 3 of password recovery. Submits the verified OTP code alongside a new password. **Revokes all active sessions** across all devices.

### Request Body Schema (`ResetPasswordRequest`)

```json
{
    "email": "john@example.com",
    "otp_code": "042819",
    "new_password": "NewSecurePassword123!",
    "website": "",
    "phone_confirm": ""
}
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "Password reset successfully. You can now log in with your new password.",
    "data": null
}
```

---

## 10. `POST /api/auth/change-password`

Changes the password for an authenticated user. **Revokes all active sessions** across all devices and clears the current session cookie.

### Request Headers

```http
Cookie: session_id=<token>
Content-Type: application/json
```

### Request Body Schema (`ChangePasswordRequest`)

```json
{
    "current_password": "Password123!",
    "new_password": "NewSecurePassword123!"
}
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "Password changed successfully. Please log in again with your new password.",
    "data": null
}
```
