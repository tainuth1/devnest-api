# Authentication Flows

This document details the core authentication and authorization lifecycle workflows implemented in the **FastAPI Authentication Boilerplate**.

---

## 1. Two-Phase Registration & Email Verification Flow

Registration uses a secure two-phase workflow to ensure email ownership before activating user accounts in PostgreSQL.

```text
[Client]                            [API Server]                       [Database / SMTP]
   │                                     │                                     │
   ├─── 1. POST /api/auth/register ─────►│                                     │
   │    {username, email, password}      ├─── Validate uniqueness & password ─►│
   │                                     ├─── Hash password & generate OTP ───►│ (Persist PendingRegistration)
   │                                     ├─── Send OTP email ─────────────────►│ (Brevo REST API)
   │◄── 200 OK (Registration pending) ───┤                                     │
   │                                     │                                     │
   ├─── 2. POST /api/auth/verify-otp ───►│                                     │
   │    {email, otp_code}                ├─── Look up PendingRegistration ────►│
   │                                     ├─── Verify expiry & attempt count ──►│
   │                                     ├─── Verify bcrypt OTP hash ─────────►│
   │                                     ├─── Create ACTIVE User row ─────────►│ (Delete PendingRegistration)
   │◄── 201 Created (User activated) ────┤                                     │
```

### Phase 1: Registration Request (`POST /api/auth/register`)

1. **Uniqueness Verification**: Checks `User.email` and `User.username` against the live database. If the email is already registered, an account enumeration defense email (`send_already_registered_email`) is sent, and a 409 Conflict is returned.
2. **Stale Clean-up**: If a previous unverified `PendingRegistration` exists for the email, it is deleted.
3. **Cryptographic OTP Generation**: A 6-digit numeric OTP is generated using `secrets.randbelow` (CSPRNG) and hashed with `bcrypt` (`hash_otp`).
4. **Persistence & Email Dispatch**: A `PendingRegistration` row is saved with a 10-minute expiration. An OTP email is dispatched via Brevo REST API.

### Phase 2: OTP Verification (`POST /api/auth/verify-otp`)

1. **Verification Checks**: Looks up `PendingRegistration` by email. Verifies that `is_expired` is false and `attempts < 5`.
2. **Attempt Counter**: Increments `attempts`. Verifies `otp_code` against `otp_hash` using constant-time verification.
3. **Activation**: Upon success, a new active `User` row is created, `PendingRegistration` is purged, and the account becomes operational.

---

## 2. Secure Login Flow & Account Lockout Guard

Login authenticates credentials, enforces account lockout guards, and returns a dual-token payload (JWT Access Token in JSON body + Refresh Token in HttpOnly cookie).

```text
[Client]                               [API Server]                         [PostgreSQL]
   │                                        │                                    │
   ├─── 1. POST /api/auth/login ───────────►│                                    │
   │    {login_id, password}                ├─── Lookup User by email/username ──►│
   │                                        ├─── Anti-timing dummy check ────────┤ (If user not found)
   │                                        ├─── Check Account Lockout ──────────┤ (If locked_until active)
   │                                        ├─── Verify Password Hash ───────────┤
   │                                        ├─── Issue HS512 Access Token ───────┤
   │                                        ├─── Save Hashed Refresh Token ─────►│ (Persist RefreshToken)
   │◄── 200 OK ─────────────────────────────┤                                    │
   │    Body: {access_token}                │                                    │
   │    Header: Set-Cookie: refresh_token   │                                    │
```

### Authentication Steps (`POST /api/auth/login`)

1. **User Lookup**: Looks up the user by email or username.
2. **Anti-Timing Attack Defense**: If the user does not exist, `verify_dummy_password()` executes a real `bcrypt` hash check against a dummy hash to preserve constant response timing.
3. **Lockout Evaluation**: Evaluates `user.is_locked_out`. If `failed_login_attempts >= 5`, the account is locked for 15 minutes (`ACCOUNT_LOCKOUT_MINUTES`). If the lockout window has elapsed, the counter is reset.
4. **Status Guard**: Blocks `SUSPENDED`, `BANNED`, or `INACTIVE` accounts.
5. **Password Verification**: On failure, `failed_login_attempts` is incremented. On success, `failed_login_attempts` is zeroed out and `last_login_at` is updated.
6. **Token Issuance**:
    - Short-lived **Access Token** (15 mins) signed with `HS512` containing `sub`, `email`, and `role`.
    - Long-lived **Refresh Token** (7 days) stored as a SHA-256 hash in PostgreSQL and sent to the client in a secure `HttpOnly`, `SameSite=Lax` cookie.

---

## 3. Refresh Token Rotation & Theft Detection Flow

Token refresh uses **Single-Use Refresh Token Rotation**. Reusing an old refresh token triggers an immediate security alert and revokes all active sessions.

```text
[Client]                               [API Server]                         [PostgreSQL]
   │                                        │                                    │
   ├─── 1. POST /api/auth/refresh ─────────►│                                    │
   │    Cookie: refresh_token=<token>       ├─── Hash token & lookup in DB ─────►│
   │                                        ├─── IF token.revoked == True: ──────┤
   │                                        │    ├── Revoke ALL user sessions ──►│ (Theft Alert!)
   │                                        │    └── Return 401 Security Alert ──┤
   │                                        │                                    │
   │                                        ├─── Revoke current token ──────────►│ (Set revoked=True)
   │                                        ├─── Issue new Refresh Token ───────►│ (Save new hash)
   │                                        ├─── Issue new Access Token ────────┤
   │◄── 200 OK ─────────────────────────────┤                                    │
   │    Body: {access_token}                │                                    │
   │    Header: Set-Cookie: refresh_token   │                                    │
```

### Rotation & Theft Prevention Algorithm (`POST /api/auth/refresh`)

1. **Token Hash Lookup**: Computes the SHA-256 hash of the incoming cookie token and queries `refresh_tokens`.
2. **Automatic Reuse & Theft Detection**: If the token record exists but `revoked == True`, an attacker or compromised client attempted to reuse a previously rotated token:
    - All active `RefreshToken` records for that user are immediately set to `revoked = True`.
    - An `AUTH_REFRESH_REVOKED_REUSE` security alert is logged.
    - A `401 Unauthorized` exception is returned requiring full re-authentication.
3. **Rotation Execution**: The existing refresh token is marked `revoked = True`. A brand-new refresh token is created, saved in PostgreSQL, and set in the response cookie. A new access token is returned.

---

## 4. Password Reset Flow

Password reset provides an out-of-band recovery process using a 6-digit OTP code sent via email.

```text
[Client]                               [API Server]                         [Database / SMTP]
   │                                        │                                    │
   ├─── 1. POST /api/auth/forgot-password ─►│                                    │
   │    {email}                             ├─── Lookup User (Enumeration safe) ─►│
   │                                        ├─── Generate & store OTP hash ─────►│ (Persist PasswordReset)
   │                                        ├─── Send Password Reset Email ──────►│ (SMTP / Brevo API)
   │◄── 200 OK ─────────────────────────────┤                                    │
   │                                        │                                    │
   ├─── 2. POST /api/auth/verify-reset-otp ►│                                    │
   │    {email, otp_code}                   ├─── Verify OTP hash & expiry ──────►│
   │◄── 200 OK ─────────────────────────────┤                                    │
   │                                        │                                    │
   ├─── 3. POST /api/auth/reset-password ──►│                                    │
   │    {email, otp_code, new_password}     ├─── Re-verify OTP ─────────────────►│
   │                                        ├─── Update User.password (bcrypt) ──►│
   │                                        ├─── Revoke ALL active sessions ────►│ (Revoke refresh tokens)
   │                                        ├─── Purge PasswordReset row ───────►│
   │◄── 200 OK ─────────────────────────────┤                                    │
```

### Steps & Safety Controls

1. **User Enumeration Prevention**: If the requested email does not exist, `forgot_password` returns a 200 OK without disclosing user existence.
2. **OTP Verification**: `verify-reset-otp` validates the 6-digit OTP code against the stored bcrypt hash and checks attempt limits.
3. **Session Invalidation**: When `reset-password` succeeds, all existing `RefreshToken` records for the user are invalidated (`revoked = True`), logging out all active sessions across all devices.

---

## 5. Password Change & Session Logout

Authenticated users can change passwords or explicitly sign out.

### Password Change (`POST /api/auth/change-password`)

- Requires valid JWT authentication (`Depends(get_current_user)`).
- Verifies `current_password` against stored `User.password`.
- Verifies that `new_password != current_password`.
- Updates `User.password` with a new bcrypt hash.
- Invalidates all existing active `RefreshToken` sessions for the account, requiring re-login on all devices.

### Session Logout (`POST /api/auth/logout`)

- Extracts the `refresh_token` from the HttpOnly request cookie.
- Sets `revoked = True` on the target `RefreshToken` in PostgreSQL.
- Clears the `refresh_token` HttpOnly cookie on the HTTP response.
