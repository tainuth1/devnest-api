# Docker Setup Reference & Blueprint Guide

This document serves as a comprehensive reference for setting up Docker and Docker Compose in a Python/FastAPI web application (or similar service architecture). It details the multi-environment Docker architecture, configuration templates, key cross-platform fixes, and step-by-step instructions for adapting this setup to a new project.

---

## 1. Architecture Overview

The Docker architecture consists of a 3-layer configuration system:

- **Base Service Configuration (`docker-compose.yml`)**: Defines shared services (`api`, `db`, `redis`), volume mounts, networking, container healthchecks, and environment file linking.
- **Development Layer (`docker-compose.dev.yml`)**: Overrides command with `--reload`, bind-mounts local source code (`.:/app`) into the container for instant hot-reloading during development.
- **Production Layer (`docker-compose.prod.yml`)**: Removes local bind mounts, configures multi-worker processes (`--workers 4`), disables debug mode (`DEBUG=false`), and uses immutable code baked into the Docker image.

```
┌─────────────────────────────────────────────────────────┐
│                    docker-compose.yml                   │
│   (Base Services: DB, Redis, API specs, Healthchecks)   │
└────────────────────────────┬────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
┌──────────────────────┐           ┌──────────────────────┐
│ docker-compose.dev.y │           │ docker-compose.prod. │
│          ml          │           │         yml          │
│ (Bind mounts,        │           │ (No volume mounts,   │
│  --reload)           │           │  Multi-worker)       │
└──────────────────────┘           └──────────────────────┘
```

---

## 2. Copy-Paste File Blueprints

### 2.1 `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install entrypoint outside /app so dev bind mounts (.:/app) do not hide or replace it
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# Fix Windows CRLF line endings issue in shell scripts
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && chmod +x /usr/local/bin/docker-entrypoint.sh

# Install system dependencies required for native compilation (e.g. psycopg2, bcrypt)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Resilient pip install against timeout/flaky mirrors
ENV PIP_DEFAULT_TIMEOUT=600
RUN pip install --no-cache-dir --retries 10 -r requirements.txt

COPY . .

EXPOSE 8000

ENTRYPOINT ["sh", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
```

### 2.2 `docker-entrypoint.sh`

```bash
#!/bin/sh
set -e

# Run database migrations and seed scripts before launching app server
python scripts/run_migrations.py
python seed.py

# Execute the primary container command (CMD from Dockerfile or docker-compose)
exec "$@"
```

### 2.3 `.dockerignore`

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
*.egg-info/
dist/
build/

# Virtual environments
.env
venv/
env/
.venv/

# Git
.git/
.gitignore

# Database files
*.db
*.sqlite3

# Uploads / Static Media (mounted as volumes when needed)
uploads/

# IDE & Editor Configs
.idea/
.vscode/

# Logs
*.log

# Docker setup files
docker-compose*.yml
Dockerfile
```

### 2.4 `docker-compose.yml` (Base Config)

```yaml
services:
    db:
        image: postgres:16-alpine
        restart: unless-stopped
        environment:
            POSTGRES_DB: ${POSTGRES_DB}
            POSTGRES_USER: ${POSTGRES_USER}
            POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
        volumes:
            - postgres_data:/var/lib/postgresql/data
        ports:
            - "5433:5432"
        healthcheck:
            test:
                ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
            interval: 5s
            timeout: 5s
            retries: 5

    redis:
        image: redis:7-alpine
        restart: unless-stopped
        ports:
            - "6379:6379"
        healthcheck:
            test: ["CMD", "redis-cli", "ping"]
            interval: 5s
            timeout: 5s
            retries: 5

    api:
        build: .
        restart: unless-stopped
        command:
            [
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-server-header",
            ]
        ports:
            - "8000:8000"
        env_file:
            - .env
        depends_on:
            db:
                condition: service_healthy
            redis:
                condition: service_healthy

volumes:
    postgres_data:
```

### 2.5 `docker-compose.dev.yml` (Development Override)

```yaml
# Local development: bind-mount source code + --reload flag
# Usage: docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

services:
    api:
        command:
            [
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--reload",
            ]
        volumes:
            - .:/app
```

### 2.6 `docker-compose.prod.yml` (Production Override)

```yaml
# Production overrides: multi-worker, no bind mount
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

services:
    api:
        command:
            [
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--workers",
                "4",
                "--no-server-header",
            ]
        environment:
            DEBUG: "false"
```

### 2.7 `.env.example`

```env
# Application
APP_NAME=My App API
APP_VERSION=1.0.0
DEBUG=True

# Database (PostgreSQL inside Docker uses service name 'db')
DATABASE_URL=postgresql://my_user:my_password@db:5432/my_db

# Redis (Redis inside Docker uses service name 'redis')
REDIS_URL=redis://redis:6379/0

# PostgreSQL credentials (consumed by db service in docker-compose)
POSTGRES_DB=my_db
POSTGRES_USER=my_user
POSTGRES_PASSWORD=my_password

# Security
SECRET_KEY=your-super-secret-key-change-this-in-production
```

---

## 3. Step-by-Step Workflow to Apply to a New Project

1. **Copy Files to New Project**:
   Copy `Dockerfile`, `docker-entrypoint.sh`, `.dockerignore`, `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.prod.yml`, and `.env.example` into your new project's root directory.

2. **Adjust Project Specifics**:
    - **Python Module Entry Point**: In `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`, and `docker-compose.prod.yml`, update `app.main:app` if your module entry point is structured differently (e.g., `src.main:app` or `main:app`).
    - **Entrypoint Tasks**: In `docker-entrypoint.sh`, update or remove `python scripts/run_migrations.py` and `python seed.py` to match your new project's database migration commands (e.g. `alembic upgrade head`).
    - **System Packages**: If your project requires other native libraries (e.g. `ffmpeg`, `libgdal-dev`), add them to `apt-get install` in `Dockerfile`.
    - **Environment Variables**: Create `.env` from `.env.example` and update database credentials and database names.

3. **Verify Line Endings on Windows**:
   Ensure `docker-entrypoint.sh` has LF line endings or rely on `sed -i 's/\r$//'` in the Dockerfile.

---

## 4. Command Reference Cheat Sheet

| Task                                  | Command                                                                                               |
| :------------------------------------ | :---------------------------------------------------------------------------------------------------- |
| **Start Dev Environment**             | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`                           |
| **Start Prod Environment (Detached)** | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d`                       |
| **Stop All Containers**               | `docker compose down`                                                                                 |
| **Stop Containers & Wipe Volumes**    | `docker compose down -v`                                                                              |
| **Run Script inside Container**       | `docker compose -f docker-compose.yml -f docker-compose.dev.yml exec api python scripts/my_script.py` |
| **Access PostgreSQL Shell**           | `docker compose exec db psql -U my_user -d my_db`                                                     |
| **Access Redis CLI**                  | `docker compose exec redis redis-cli`                                                                 |
| **View API Logs**                     | `docker compose logs -f api`                                                                          |

---

## 5. Key Pitfalls & Solutions Explained

| Issue / Gotcha                                           | Why It Happens                                                              | Solution Implemented                                                                   |
| :------------------------------------------------------- | :-------------------------------------------------------------------------- | :------------------------------------------------------------------------------------- |
| `exec ./docker-entrypoint.sh: no such file or directory` | Local dev volume mount (`.:/app`) overwrites container's `/app` folder.     | Copy script to `/usr/local/bin/docker-entrypoint.sh` outside `/app`.                   |
| `/bin/sh\r: no such file or directory`                   | Windows git checkout formats shell scripts with CRLF (`\r\n`) line breaks.  | Run `sed -i 's/\r$//'` in `Dockerfile` before setting permissions.                     |
| API crashes on startup because DB isn't ready            | Container starts before Postgres finishes initializing sockets.             | Configure `healthcheck` on `db` and `depends_on: condition: service_healthy` on `api`. |
| `pip install` fails with read timeout                    | Default 15s pip timeout hits slow network/PyPI mirrors during Docker build. | Set `ENV PIP_DEFAULT_TIMEOUT=600` and `pip install --retries 10`.                      |
