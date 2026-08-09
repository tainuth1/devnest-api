# User Roles & Database Seeding Guide

This guide details the Role-Based Access Control (RBAC) permissions hierarchy and the database seeder script in the **FastAPI Authentication Boilerplate**.

---

## User Roles & Authorization Hierarchy

The application defines three distinct roles using the `UserRole` string enum in `app/core/enums.py`:

```python
class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    DEVELOPER = "developer"
```

### Role Definitions & Capabilities

| Role        | Access Level       | Description & Capabilities                                                                                                                                                                                         |
| :---------- | :----------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `user`      | Standard           | Default role assigned upon self-registration. Access limited to personal profile management (`/api/auth/me`), password updates, and non-privileged application endpoints.                                          |
| `admin`     | Administrative     | Administrative access. Granted permission to view system-wide user lists, search user profiles, update user account statuses (`active`, `suspended`, `banned`), and inspect system audit logs (`/api/audit-logs`). |
| `developer` | Superuser / System | System developer and maintenance role. Inherits all `admin` privileges with full system oversight, raw database inspection privileges, and developer diagnostics access.                                           |

---

## Pre-Seeded Default Accounts

The database seeder script creates three initial system accounts—one for each role—allowing instant login and testing after installation.

| Role        | Username            | Default Email           | Default Password       | Initial Status |
| :---------- | :------------------ | :---------------------- | :--------------------- | :------------- |
| `user`      | `default_user`      | `user@example.com`      | `UserDefault123!`      | `ACTIVE`       |
| `admin`     | `default_admin`     | `admin@example.com`     | `AdminDefault123!`     | `ACTIVE`       |
| `developer` | `default_developer` | `developer@example.com` | `DeveloperDefault123!` | `ACTIVE`       |

---

## Environment Variable Seeder Overrides

You can override the default credentials by defining environment variables in your `.env` file before executing the seeder or running Docker Compose.

### Override Variables Reference

| Target Account    | Environment Variable  | Description                             | Default Value           |
| :---------------- | :-------------------- | :-------------------------------------- | :---------------------- |
| **Standard User** | `SEED_USER_USERNAME`  | Username override for default user      | `default_user`          |
|                   | `SEED_USER_EMAIL`     | Email override for default user         | `user@example.com`      |
|                   | `SEED_USER_PASSWORD`  | Password override for default user      | `UserDefault123!`       |
| **Admin**         | `SEED_ADMIN_USERNAME` | Username override for default admin     | `default_admin`         |
|                   | `SEED_ADMIN_EMAIL`    | Email override for default admin        | `admin@example.com`     |
|                   | `SEED_ADMIN_PASSWORD` | Password override for default admin     | `AdminDefault123!`      |
| **Developer**     | `SEED_DEV_USERNAME`   | Username override for default developer | `default_developer`     |
|                   | `SEED_DEV_EMAIL`      | Email override for default developer    | `developer@example.com` |
|                   | `SEED_DEV_PASSWORD`   | Password override for default developer | `DeveloperDefault123!`  |

### Example `.env` Overrides

```env
# Custom Seeded Credentials
SEED_USER_USERNAME=john_doe
SEED_USER_EMAIL=john@example.com
SEED_USER_PASSWORD=MyCustomUserPass123!

SEED_ADMIN_USERNAME=sys_admin
SEED_ADMIN_EMAIL=admin@company.com
SEED_ADMIN_PASSWORD=MyCustomAdminPass123!

SEED_DEV_USERNAME=lead_dev
SEED_DEV_EMAIL=dev@company.com
SEED_DEV_PASSWORD=MyCustomDevPass123!
```

---

## Seeder Execution Guide (`scripts/seed_users.py`)

The database seeder is powered by `scripts/seed_users.py`.

### Key Behaviors & Idempotency

- **Automatic Execution**: When running via Docker, `docker-entrypoint.sh` runs `python scripts/seed_users.py` automatically after `alembic upgrade head`.
- **Idempotent Execution**: The script checks if a user with the specified email or username already exists. If found, creation is skipped without error.
- **Password Security**: Passwords are automatically hashed with `bcrypt` (via `passlib`) before insertion.
- **Log Sanitization**: Logs sanitize sensitive inputs using `sanitize_for_log` to avoid exposing credentials.

### Running the Seeder Script Manually

#### Native Environment (Virtualenv Active):

```bash
python scripts/seed_users.py
```

#### Docker Compose Environment:

```bash
docker compose exec api python scripts/seed_users.py
```

### Expected Output Example

```text
2026-08-09 11:30:00,123 | INFO | ==> Successfully created default user: email=user@example.com username=default_user (role=user)
2026-08-09 11:30:00,456 | INFO | ==> Successfully created default user: email=admin@example.com username=default_admin (role=admin)
2026-08-09 11:30:00,789 | INFO | ==> Successfully created default user: email=developer@example.com username=default_developer (role=developer)
2026-08-09 11:30:00,790 | INFO | ==> Seeding completed. Created: 3, Skipped (already exist): 0
```
