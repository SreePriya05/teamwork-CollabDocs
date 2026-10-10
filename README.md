# CollabDocs

CollabDocs is an API-only collaborative document management platform built with Django and Django REST Framework.

## Current Scope

This initial setup creates the project shell and app boundaries for:

- `accounts`
- `workspaces`
- `documents`
- `comments`
- `auditlogs`

Workspace, document, document versioning, users, comments, tags, audit logs, signals, and middleware business logic is intentionally not implemented yet.

## Requirements

- Python 3.12 or newer
- PostgreSQL

## Setup

Create and activate a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create local environment settings:

```powershell
Copy-Item .env.example .env
```

Update `.env` with your local PostgreSQL credentials, then run:

```powershell
python manage.py check
python manage.py migrate
python manage.py runserver
```

The API health check is available at:

```text
GET /api/health/
```

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret key for the environment |
| `DJANGO_DEBUG` | Enables debug mode when true |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `POSTGRES_DB` | PostgreSQL database name |
| `POSTGRES_USER` | PostgreSQL username |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `POSTGRES_HOST` | PostgreSQL host |
| `POSTGRES_PORT` | PostgreSQL port |

## Development Notes

- PostgreSQL is required; SQLite is not configured.
- Authentication uses the shared custom `accounts.User` model configured by `AUTH_USER_MODEL`.
- Application models should inherit from `common.models.UUIDPrimaryKeyModel` or define an equivalent UUID primary key when implemented.
- Keep business logic inside the owning app to reduce merge conflicts between developers.
