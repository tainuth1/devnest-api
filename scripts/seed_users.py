"""
Database Seeder Script.

Creates three default system users with different roles (user, admin, developer)
if they do not already exist in the database.

Idempotent: Safe to run repeatedly — existing users are skipped.
"""

import os
import sys
import logging

# Ensure project root is in sys.path when script is executed directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.modules.auth.models import User
from app.core.enums import UserRole, UserStatus
from app.core.security import hash_password
from app.core.sanitize import sanitize_for_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("seed_users")

# Default user credentials (can be overridden via environment variables)
DEFAULT_USERS = [
    {
        "username": os.getenv("SEED_USER_USERNAME", "default_user"),
        "email": os.getenv("SEED_USER_EMAIL", "user@example.com"),
        "password": os.getenv("SEED_USER_PASSWORD", "UserDefault123!"),
        "first_name": "Default",
        "last_name": "User",
        "role": UserRole.USER,
    },
    {
        "username": os.getenv("SEED_ADMIN_USERNAME", "default_admin"),
        "email": os.getenv("SEED_ADMIN_EMAIL", "admin@example.com"),
        "password": os.getenv("SEED_ADMIN_PASSWORD", "AdminDefault123!"),
        "first_name": "Default",
        "last_name": "Admin",
        "role": UserRole.ADMIN,
    },
    {
        "username": os.getenv("SEED_DEV_USERNAME", "default_developer"),
        "email": os.getenv("SEED_DEV_EMAIL", "developer@example.com"),
        "password": os.getenv("SEED_DEV_PASSWORD", "DeveloperDefault123!"),
        "first_name": "Default",
        "last_name": "Developer",
        "role": UserRole.DEVELOPER,
    },
]


def seed_default_users() -> None:
    """Seed default users for user, admin, and developer roles if not present."""
    db = SessionLocal()
    try:
        created_count = 0
        skipped_count = 0

        for user_data in DEFAULT_USERS:
            email = user_data["email"].lower().strip()
            username = user_data["username"].lower().strip()

            # Check if user already exists by email or username
            existing_user = (
                db.query(User)
                .filter((User.email == email) | (User.username == username))
                .first()
            )

            if existing_user:
                logger.info(
                    "==> User already exists: email=%s username=%s (role=%s) — Skipping creation.",
                    sanitize_for_log(existing_user.email),
                    sanitize_for_log(existing_user.username or ""),
                    existing_user.role.value,
                )
                skipped_count += 1
                continue

            # Create new user
            new_user = User(
                username=username,
                email=email,
                password=hash_password(user_data["password"]),
                first_name=user_data["first_name"],
                last_name=user_data["last_name"],
                role=user_data["role"],
                status=UserStatus.ACTIVE,
            )

            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            logger.info(
                "==> Successfully created default user: email=%s username=%s (role=%s)",
                sanitize_for_log(new_user.email),
                sanitize_for_log(new_user.username or ""),
                new_user.role.value,
            )
            created_count += 1

        logger.info(
            "==> Seeding completed. Created: %d, Skipped (already exist): %d",
            created_count,
            skipped_count,
        )

    except Exception as exc:
        db.rollback()
        logger.error("==> Error during user seeding: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_default_users()
