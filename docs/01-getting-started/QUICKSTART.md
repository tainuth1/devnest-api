# Quickstart Guide

Welcome to the **FastAPI Authentication Boilerplate** Quickstart Guide. This document provides step-by-step instructions for getting the application up and running locally, both natively (using Python and PostgreSQL) and with Docker Compose.

---

## Prerequisites

Before you begin, ensure you have the following installed on your system:

| Tool               | Minimum Version | Description                                               |
| :----------------- | :-------------- | :-------------------------------------------------------- |
| **Python**         | `3.11+`         | Runtime environment for local development                 |
| **PostgreSQL**     | `16.0+`         | Relational database (required for local non-Docker setup) |
| **Docker Engine**  | `20.10+`        | Container runtime                                         |
| **Docker Compose** | `v2.0+`         | Multi-container orchestration tool                        |
| **Git**            | `2.x+`          | Source control manager                                    |

---

## 1. Repository Setup & Environment Configuration

### 1.1 Clone the Repository

Clone the project repository to your local machine and navigate into the project directory:

```bash
git clone https://github.com/your-username/fastapi-authentication-boilerplate.git
cd fastapi-authentication-boilerplate
```

### 1.2 Create the `.env` File

Copy the provided environment template `.env.example` to create your local `.env` configuration:

```bash
# On Linux / macOS / Git Bash
cp .env.example .env

# On Windows PowerShell
Copy-Item .env.example .env
```

### 1.3 Generate a Secure `SECRET_KEY`

The application requires a strong 64-byte secret key for signing JWTs (using `HS512`) and calculating cryptographic HMAC data integrity signatures.

Choose one of the commands below to generate a secure random string:

#### **PowerShell (Windows):**

```powershell
$rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::new()
$bytes = New-Object byte[] 64
$rng.GetBytes($bytes)
[System.Convert]::ToBase64String($bytes)
```

#### **Python (Cross-platform):**

```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

#### **OpenSSL (Linux / macOS):**

```bash
openssl rand -hex 64
```

Copy the generated key into your `.env` file for the `SECRET_KEY` variable:

```env
SECRET_KEY=your_generated_64_byte_secret_key_here
```

---

## 2. Local Setup (Native Python & PostgreSQL)

Follow these steps if you want to run the FastAPI application directly on your local system without Docker.

### 2.1 Virtual Environment Setup

Create and activate a Python virtual environment:

#### **Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

#### **Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### **Windows (Command Prompt):**

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

### 2.2 Install Dependencies

Upgrade `pip` and install all required project packages:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.3 Database Setup & Migration

Ensure PostgreSQL is running on your system, and create a database and user matching your `.env` file settings:

```sql
CREATE DATABASE auth_boilerplate_db;
CREATE USER auth_boilerplate_user WITH PASSWORD 'auth_boilerplate_pass';
GRANT ALL PRIVILEGES ON DATABASE auth_boilerplate_db TO auth_boilerplate_user;
```

Update your `.env` file `DATABASE_URL`:

```env
DATABASE_URL=postgresql://auth_boilerplate_user:auth_boilerplate_pass@localhost:5432/auth_boilerplate_db
```

Apply database migrations using Alembic:

```bash
alembic upgrade head
```

_(Optional)_ Seed default accounts (`user`, `admin`, `developer`):

```bash
python scripts/seed_users.py
```

### 2.4 Run Development Server with Uvicorn

Start the local Uvicorn development server with live reload enabled:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API server is now running at `http://127.0.0.1:8000`.

---

## 🐳 3. Running with Docker Compose

Docker Compose manages both the FastAPI application server and the PostgreSQL database container automatically.

### 3.1 Development Mode (Hot-Reloading)

In development mode, code changes on your host machine instantly update inside the container without rebuilding:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

> [!NOTE]
> On startup, `docker-entrypoint.sh` automatically runs `alembic upgrade head` and `python scripts/seed_users.py` before starting the Uvicorn dev server.

### 3.2 Production Mode (Multi-Worker Execution)

Production mode runs Uvicorn with 4 background workers and detaches the container process:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

### 3.3 Container Management Commands

| Action                                | Command                                                                       |
| :------------------------------------ | :---------------------------------------------------------------------------- |
| **View API logs**                     | `docker compose logs -f api`                                                  |
| **View Database logs**                | `docker compose logs -f db`                                                   |
| **Stop containers**                   | `docker compose down`                                                         |
| **Stop containers & wipe DB storage** | `docker compose down -v`                                                      |
| **Access PostgreSQL shell**           | `docker compose exec db psql -U auth_boilerplate_user -d auth_boilerplate_db` |
| **Re-run User Seeder**                | `docker compose exec api python scripts/seed_users.py`                        |

---

## 4. Interactive API Documentation

When `DEBUG=True` in your `.env` file, FastAPI automatically generates interactive API documentation.

### 4.1 OpenAPI / Swagger UI

Navigate to `http://localhost:8000/docs` in your browser to interactively test endpoints, authorize requests using JWT Bearer tokens, and inspect request/response schemas.

### 4.2 ReDoc

Navigate to `http://localhost:8000/redoc` for a clean, human-readable documentation view designed for front-end integration and API reference.

> [!WARNING]
> In production (`DEBUG=False`), `/docs`, `/redoc`, and `/openapi.json` are automatically disabled to prevent unauthorized schema exposure and adhere to OWASP A05 Security Misconfiguration best practices.

---

## Default Seeded Accounts

If you ran the user seeder (`scripts/seed_users.py`), the following accounts are available for initial login testing:

| Role          | Username            | Email                   | Default Password       |
| :------------ | :------------------ | :---------------------- | :--------------------- |
| **User**      | `default_user`      | `user@example.com`      | `UserDefault123!`      |
| **Admin**     | `default_admin`     | `admin@example.com`     | `AdminDefault123!`     |
| **Developer** | `default_developer` | `developer@example.com` | `DeveloperDefault123!` |

> [!IMPORTANT]
> You can override these default credentials by defining `SEED_USER_*`, `SEED_ADMIN_*`, or `SEED_DEV_*` variables in your `.env` file before initial startup.
