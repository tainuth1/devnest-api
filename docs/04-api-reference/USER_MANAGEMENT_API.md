# User Management API Reference

This document provides technical reference documentation for the User Management & System Information endpoints mounted under `/api/admin` in the **FastAPI Authentication Boilerplate**.

Base Path: `/api/admin`

---

## Endpoint Summary

| Method  | Path                                | Summary                    | Auth Required | Permitted Roles      |
| :------ | :---------------------------------- | :------------------------- | :------------ | :------------------- |
| `GET`   | `/api/admin/users`                  | List all users (paginated) | Bearer Token  | `admin`              |
| `GET`   | `/api/admin/users/{user_id}`        | Get user details by UUID   | Bearer Token  | `admin`              |
| `PATCH` | `/api/admin/users/{user_id}/status` | Update user account status | Bearer Token  | `admin`              |
| `GET`   | `/api/admin/system/info`            | Get system status & stats  | Bearer Token  | `admin`, `developer` |

---

## 1. `GET /api/admin/users`

Retrieves a paginated list of all registered users in the system.

### Authorization

- **Requires `admin` role**. Non-admin users receive a `403 Forbidden` error.

### Query Parameters

| Parameter | Type  | Default | Constraints      | Description                                      |
| :-------- | :---- | :------ | :--------------- | :----------------------------------------------- |
| `skip`    | `int` | `0`     | `ge=0`           | Number of records to skip for pagination offset. |
| `limit`   | `int` | `50`    | `ge=1`, `le=100` | Maximum number of records to return per page.    |

### Request Headers

```http
Authorization: Bearer <admin_access_token>
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "Returned 3 users.",
    "data": {
        "users": [
            {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "username": "default_user",
                "role": "user",
                "status": "active",
                "first_name": "Default",
                "last_name": "User",
                "created_at": "2026-08-09T10:00:00+00:00",
                "updated_at": "2026-08-09T10:00:00+00:00",
                "last_login_at": "2026-08-09T11:00:00+00:00"
            }
        ],
        "skip": 0,
        "limit": 50,
        "total": 3
    }
}
```

### cURL Example

```bash
curl -X GET "http://localhost:8000/api/admin/users?skip=0&limit=10" \
  -H "Authorization: Bearer <admin_access_token>"
```

---

## 2. `GET /api/admin/users/{user_id}`

Retrieves full profile details for a specific user identified by UUID.

### Authorization

- **Requires `admin` role**.

### Path Parameters

| Parameter | Type   | Description                              |
| :-------- | :----- | :--------------------------------------- |
| `user_id` | `UUID` | Unique ID of the target user to inspect. |

### Request Headers

```http
Authorization: Bearer <admin_access_token>
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "User details retrieved successfully.",
    "data": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "email": "user@example.com",
        "username": "default_user",
        "role": "user",
        "status": "active",
        "first_name": "Default",
        "last_name": "User",
        "created_at": "2026-08-09T10:00:00+00:00",
        "updated_at": "2026-08-09T10:00:00+00:00",
        "last_login_at": "2026-08-09T11:00:00+00:00"
    }
}
```

### Error Responses

- `404 Not Found`: Target user ID does not exist.

```json
{
    "status": 404,
    "success": false,
    "message": "User not found.",
    "data": null
}
```

### cURL Example

```bash
curl -X GET "http://localhost:8000/api/admin/users/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <admin_access_token>"
```

---

## 3. `PATCH /api/admin/users/{user_id}/status`

Updates the account status (`active`, `inactive`, `suspended`, `banned`) of a targeted user account.

### Authorization

- **Requires `admin` role**.
- **Self-Mutation Restriction**: Administrators cannot change their own account status.

### Request Body Schema (`UpdateUserStatusRequest`)

```json
{
    "status": "suspended"
}
```

- `status` (`UserStatus` Enum, required): Must be one of `"active"`, `"inactive"`, `"suspended"`, or `"banned"`.

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "User status updated to 'suspended'.",
    "data": {
        "user_id": "123e4567-e89b-12d3-a456-426614174000",
        "status": "suspended"
    }
}
```

### Error Responses

- `400 Bad Request`: Administrator attempts to change their own status.

```json
{
    "status": 400,
    "success": false,
    "message": "Admins cannot change their own status.",
    "data": null
}
```

### cURL Example

```bash
curl -X PATCH "http://localhost:8000/api/admin/users/123e4567-e89b-12d3-a456-426614174000/status" \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "suspended"
  }'
```

---

## 4. `GET /api/admin/system/info`

Retrieves system diagnostics, application version details, and user count statistics.

### Authorization

- **Requires `admin` or `developer` role**.

### Request Headers

```http
Authorization: Bearer <access_token>
```

### Response (200 OK)

```json
{
    "status": 200,
    "success": true,
    "message": "System info retrieved.",
    "data": {
        "app_name": "FastAPI Authentication Boilerplate",
        "app_version": "1.0.0",
        "current_time": "2026-08-09T11:43:00+00:00",
        "total_users": 3,
        "active_users": 3
    }
}
```

### cURL Example

```bash
curl -X GET "http://localhost:8000/api/admin/system/info" \
  -H "Authorization: Bearer <access_token>"
```
