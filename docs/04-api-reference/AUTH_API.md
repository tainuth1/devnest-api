# Authentication API Reference

This document provides a technical specification for all endpoints under `/api/auth` in the **FastAPI Authentication Boilerplate**.

Base Path: `/api/auth`

---

## Endpoint Summary

| Method        | Path                         | Summary                              | Auth Required | Rate Limit     |
| :------------ | :--------------------------- | :----------------------------------- | :------------ | :------------- |
| `POST`        | `/api/auth/register`         | Phase 1: Register account & send OTP | No            | 3/10min, 10/hr |
| `POST`        | `/api/auth/verify-otp`       | Phase 2: Verify registration OTP     | No            | 7/min, 20/hr   |
| `POST`        | `/api/auth/login`            | Authenticate & issue JWT / Cookie    | No            | 7/min, 30/hr   |
| `POST`        | `/api/auth/refresh`          | Rotate refresh token & issue JWT     | Cookie        | 30/min         |
| `POST`        | `/api/auth/logout`           | Revoke session & clear cookie        | Cookie        | 30/min         |
| `GET`         | `/api/auth/me`               | Get current user profile             | Bearer Token  | 60/min         |
| `PUT`/`PATCH` | `/api/auth/me`               | Update current user profile          | Bearer Token  | 10/min, 30/hr  |
| `POST`        | `/api/auth/forgot-password`  | Phase 1: Request password reset OTP  | No            | 3/10min, 10/hr |
| `POST`        | `/api/auth/verify-reset-otp` | Phase 2: Verify reset OTP code       | No            | 7/min, 20/hr   |
| `POST`        | `/api/auth/reset-password`   | Phase 3: Reset password with OTP     | No            | 7/min, 20/hr   |
| `POST`        | `/api/auth/change-password`  | Change password for active account   | Bearer Token  | 10/min, 30/hr  |

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
    "first_name": "John",
    "last_name": "Doe",
    "website": "",
    "phone_confirm": ""
}
```

- `username` (`str`, optional): 3-50 characters.
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

Authenticates user credentials and issues a JWT Access Token in the response body alongside an `HttpOnly` Refresh Token cookie.

### Request Body Schema (`LoginRequest`)

```json
{
    "login_id": "john@example.com",
    "password": "Password123!",
    "website": "",
    "phone_confirm": ""
}
```

- `login_id` (`str`): User's email or username.

### Response Headers

```http
Set-Cookie: refresh_token=abc123...; Path=/; HttpOnly; SameSite=Lax
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
        },
        "tokens": {
            "access_token": "eyJhbGciOiJIUzUxMi...",
            "token_type": "bearer",
            "expires_in": 900
        }
    }
}
```

### cURL Example

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{
    "login_id": "john@example.com",
    "password": "Password123!"
  }'
```

---

## 4. `POST /api/auth/refresh`

Rotates the single-use refresh token cookie and returns a new short-lived access token.

### Request Headers

```http
Cookie: refresh_token=<token_string>
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "Tokens refreshed successfully.",
    "data": {
        "tokens": {
            "access_token": "eyJhbGciOiJIUzUxMi...",
            "token_type": "bearer",
            "expires_in": 900
        }
    }
}
```

### cURL Example

```bash
curl -X POST "http://localhost:8000/api/auth/refresh" \
  -b cookies.txt \
  -c cookies.txt
```

---

## 5. `POST /api/auth/logout`

Revokes the active refresh token session in PostgreSQL and clears the `HttpOnly` refresh token cookie.

### Request Headers

```http
Cookie: refresh_token=<token_string>
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

## 6. `GET /api/auth/me`

Fetches the profile details of the currently authenticated user.

### Request Headers

```http
Authorization: Bearer <access_token>
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
  -H "Authorization: Bearer <your_access_token>"
```

---

## 7. `PUT` / `PATCH /api/auth/me`

Updates profile details for the authenticated user.

### Request Headers

```http
Authorization: Bearer <access_token>
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

## 8. `POST /api/auth/forgot-password`

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

## 9. `POST /api/auth/verify-reset-otp`

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

## 10. `POST /api/auth/reset-password`

Phase 3 of password recovery. Submits the verified OTP code alongside a new password.

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

## 11. `POST /api/auth/change-password`

Changes the password for an authenticated user. Invalidates all active refresh tokens/sessions across all devices.

### Request Headers

```http
Authorization: Bearer <access_token>
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
