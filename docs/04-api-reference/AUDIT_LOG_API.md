# Security Audit Log API Reference

This document provides technical reference documentation for the Security Audit Log endpoint mounted under `/api/admin/audit-logs` in the **FastAPI Authentication Boilerplate**.

Base Path: `/api/admin/audit-logs`

---

## Endpoint Summary

| Method | Path                    | Summary                                    | Auth Required | Permitted Roles      |
| :----- | :---------------------- | :----------------------------------------- | :------------ | :------------------- |
| `GET`  | `/api/admin/audit-logs` | List & filter database security audit logs | Bearer Token  | `admin`, `developer` |

---

## 1. `GET /api/admin/audit-logs`

Retrieves a paginated, filterable list of security audit event records stored in PostgreSQL.

### Authorization

- **Requires `admin` or `developer` role** (`Depends(require_admin_or_developer)`).
- Regular users (`user` role) receive a `403 Forbidden` error.

### Query Parameters

| Parameter    | Type   | Default | Constraints      | Description                                                                                              |
| :----------- | :----- | :------ | :--------------- | :------------------------------------------------------------------------------------------------------- |
| `user_id`    | `UUID` | `None`  | Optional         | Filter audit events by target user UUID.                                                                 |
| `event_type` | `str`  | `None`  | Optional         | Filter by event type string (e.g. `AUTH_LOGIN_SUCCESS`, `HONEYPOT_TRIGGERED`, `INTEGRITY_CHECK_FAILED`). |
| `status`     | `str`  | `None`  | Optional         | Filter by audit status (`SUCCESS`, `FAILURE`, `BLOCKED`, `ALERT`).                                       |
| `skip`       | `int`  | `0`     | `ge=0`           | Number of records to skip for pagination offset.                                                         |
| `limit`      | `int`  | `50`    | `ge=1`, `le=100` | Maximum number of records to return per page (capped at 100).                                            |

### Request Headers

```http
Authorization: Bearer <access_token>
```

### Response Schema (`AuditLogListResponse`)

```json
{
    "status": 200,
    "success": true,
    "message": "Audit logs retrieved successfully.",
    "data": {
        "items": [
            {
                "id": "7b8e4567-e89b-12d3-a456-426614174000",
                "event_type": "AUTH_LOGIN_SUCCESS",
                "status": "SUCCESS",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_email": "user@example.com",
                "user_username": "default_user",
                "client_ip": "127.0.0.1",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
                "request_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
                "details": {
                    "method": "POST",
                    "path": "/api/auth/login"
                },
                "created_at": "2026-08-09T11:00:00+00:00"
            }
        ],
        "total": 45,
        "skip": 0,
        "limit": 50
    }
}
```

### Error Responses

#### 401 Unauthorized

Returned when authentication Bearer credentials are missing or invalid.

```json
{
    "status": 401,
    "success": false,
    "message": "Authentication credentials were not provided.",
    "data": null
}
```

#### 403 Forbidden

Returned when an authenticated user attempts access without `admin` or `developer` permissions.

```json
{
    "status": 403,
    "success": false,
    "message": "You do not have permission to perform this action.",
    "data": null
}
```

---

## cURL Examples

### 1. Retrieve Recent Audit Logs (Default Pagination)

```bash
curl -X GET "http://localhost:8000/api/admin/audit-logs" \
  -H "Authorization: Bearer <access_token>"
```

### 2. Filter Audit Logs by Event Type & Status

```bash
curl -X GET "http://localhost:8000/api/admin/audit-logs?event_type=HONEYPOT_TRIGGERED&status=BLOCKED" \
  -H "Authorization: Bearer <access_token>"
```

### 3. Filter Audit Logs by User ID with Custom Page Size

```bash
curl -X GET "http://localhost:8000/api/admin/audit-logs?user_id=123e4567-e89b-12d3-a456-426614174000&skip=0&limit=25" \
  -H "Authorization: Bearer <access_token>"
```
