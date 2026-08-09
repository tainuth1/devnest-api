#!/bin/sh
set -e

# Run database migrations before launching the app server
echo "==> Running database migrations (alembic)..."
alembic upgrade head

# Seed default system users (user, admin, developer) if they do not exist
echo "==> Seeding default system users..."
python scripts/seed_users.py

# Execute the primary container command (CMD from Dockerfile or docker-compose)
exec "$@"
