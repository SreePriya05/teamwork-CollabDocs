# CollabDocs

CollabDocs is an API-only collaborative document platform built with Django and Django REST Framework. It covers users, workspaces, documents and versions, comments, tags, and audit logs.

## Requirements

- Python 3.12 or newer
- PostgreSQL 16 or newer
- Docker, when using the Compose database below

## Startup

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, create and activate the environment with `py -3.12 -m venv .venv` and `.\.venv\Scripts\Activate.ps1`, then copy the env file with `Copy-Item .env.example .env`.

### Database

Docker Compose starts Postgres and publishes it on the port in `.env` (`5433` in `.env.example`):

```bash
docker compose up -d db
```

To use a Postgres instance that is already running, set `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in `.env` to that instance. Create the role and database first if they do not exist.

### App

```bash
python manage.py migrate
python manage.py runserver
```

The API is then available at `http://127.0.0.1:8000`.

Workspace and document routes require authentication. Public registration does not set a password, so create a user that can sign in with HTTP Basic auth:

```bash
python manage.py shell -c '
from accounts.models import User
user = User.objects.create_user(
    email="ada@example.com",
    password="test-password",
    first_name="Ada",
    last_name="Lovelace",
    phone="9876543210",
)
print(user.id)
'
```

Send that email and password as Basic auth (`-u ada@example.com:test-password` with curl). Accounts, comments, tags, and audit logs are open.

## Testing the API

Run the automated suite. Tests use an in-memory SQLite database and do not need Postgres:

```bash
python manage.py test
```

The checks below exercise the running server. Save ids from each JSON response and reuse them in the next call. Examples use `http://127.0.0.1:8000`.

### Health

```bash
curl http://127.0.0.1:8000/api/health/
```

Expected: `200` and `{"status":"ok"}`.

### Accounts

Register a user. The email is stored in lowercase.

```bash
curl -X POST http://127.0.0.1:8000/api/accounts/users/ \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Grace","last_name":"Hopper","email":"Grace@Example.com","phone":"1234567890"}'
```

Then retrieve and list users:

```bash
curl http://127.0.0.1:8000/api/accounts/users/<user-id>/
curl http://127.0.0.1:8000/api/accounts/users/
```

A duplicate email or a phone that is not exactly 10 digits returns `400`. The retrieve payload includes `comment_count`.

### Workspaces

Create a workspace as Ada. She becomes the owner and an admin member.

```bash
curl -u ada@example.com:test-password \
  -X POST http://127.0.0.1:8000/api/workspaces/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Research"}'
```

```bash
curl -u ada@example.com:test-password http://127.0.0.1:8000/api/workspaces/<workspace-id>/
curl -u ada@example.com:test-password http://127.0.0.1:8000/api/workspaces/<workspace-id>/members/
curl -u ada@example.com:test-password http://127.0.0.1:8000/api/workspaces/<workspace-id>/summary/
```

Add a member with `role` set to `admin`, `editor`, or `viewer`:

```bash
curl -u ada@example.com:test-password \
  -X POST http://127.0.0.1:8000/api/workspaces/<workspace-id>/members/ \
  -H "Content-Type: application/json" \
  -d '{"user":"<user-id>","role":"viewer"}'
```

Anonymous calls return `403`. A signed-in user who is not a member receives `404`. Adding the same user again returns `409`. Only admins can add members.

### Documents

Editors and admins can create a document. The response includes `version_count` of `1`.

```bash
curl -u ada@example.com:test-password \
  -X POST http://127.0.0.1:8000/api/documents/ \
  -H "Content-Type: application/json" \
  -d '{"title":"Notes","content":"First draft","workspace":"<workspace-id>","status":"draft"}'
```

List supports `workspace`, repeated `status`, `search` (title), and `tag`:

```bash
curl -u ada@example.com:test-password \
  "http://127.0.0.1:8000/api/documents/?workspace=<workspace-id>&status=draft&search=note"
```

Replace the document. Each successful update stores the next version.

```bash
curl -u ada@example.com:test-password \
  -X PUT http://127.0.0.1:8000/api/documents/<document-id>/ \
  -H "Content-Type: application/json" \
  -d '{"title":"Notes","content":"Second draft","workspace":"<workspace-id>","status":"published"}'
```

```bash
curl -u ada@example.com:test-password http://127.0.0.1:8000/api/documents/<document-id>/versions/
curl -u ada@example.com:test-password http://127.0.0.1:8000/api/documents/<document-id>/stats/
```

`status` is `draft`, `published`, or `archived`. A viewer can read and cannot create, update, or attach tags. A conflicting version number returns `409`.

Attach tags by name, by existing tag id, or both. Names are created when they do not exist. The response includes `tags` and `tag_names`.

```bash
curl -u ada@example.com:test-password \
  -X POST http://127.0.0.1:8000/api/documents/<document-id>/tags/ \
  -H "Content-Type: application/json" \
  -d '{"tags":["python","django"],"tag_ids":["<tag-id>"]}'

curl -u ada@example.com:test-password http://127.0.0.1:8000/api/documents/<document-id>/tags/
```

### Comments and tags

```bash
curl -X POST http://127.0.0.1:8000/api/comments/comments/ \
  -H "Content-Type: application/json" \
  -d '{"document":"<document-id>","author":"<user-id>","content":"Looks good"}'
```

Reply with the parent comment id. The parent must belong to the same document.

```bash
curl -X POST http://127.0.0.1:8000/api/comments/comments/ \
  -H "Content-Type: application/json" \
  -d '{"document":"<document-id>","author":"<user-id>","content":"A reply","parent":"<comment-id>"}'
```

```bash
curl "http://127.0.0.1:8000/api/comments/comments/?document=<document-id>"
curl http://127.0.0.1:8000/api/comments/comments/<comment-id>/
```

The list returns top-level comments with `reply_count` and nested `replies`. Blank content returns `400`.

Create and search tags. Names are trimmed and lowercased.

```bash
curl -X POST http://127.0.0.1:8000/api/comments/tags/ \
  -H "Content-Type: application/json" \
  -d '{"name":" Python "}'

curl "http://127.0.0.1:8000/api/comments/tags/?search=py"
```

A duplicate tag name returns `400`.

### Audit logs

Document creates and updates are written automatically.

```bash
curl "http://127.0.0.1:8000/api/auditlogs/audit-logs/?model_name=Document&actor=<user-id>"
curl http://127.0.0.1:8000/api/auditlogs/audit-logs/<audit-log-id>/
curl http://127.0.0.1:8000/api/auditlogs/audit-logs/summary/
```

The summary returns `total`, `created_count`, and `updated_count`. Filters also accept `actor_id`, `start` or `start_date`, and `end` or `end_date`. `POST` returns `405`. The same list is available at `/api/auditlogs/auditlogs/`.

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
| `POSTGRES_PORT` | PostgreSQL port published by Compose, or the port of a local server |

## Development Notes

- Authentication uses the custom `accounts.User` model (`AUTH_USER_MODEL`). Sign in with the email address.
- `python manage.py test` swaps the database to in-memory SQLite. The development server uses PostgreSQL.
- Keep business logic inside the owning app.

## API reference

Import `postman/CollabDocs.postman_collection.json` into Postman. The collection variable `baseUrl` is `http://127.0.0.1:8000`. `email` and `password` match the shell user in Startup (`ada@example.com` / `test-password`). Run the folder from top to bottom: each request stores the next id (`memberUserId`, `workspaceId`, `documentId`, `commentId`, `tagId`, `auditLogId`).

Create that shell user before running the Workspaces or Documents folders. Accounts, comments, tags, and audit logs do not send the Basic auth header.

| Method | Path | Auth | Success | Notes |
| --- | --- | --- | --- | --- |
| GET | `/api/health/` | No | 200 | `{"status":"ok"}` |
| POST | `/api/accounts/users/` | No | 201 | Register. Does not set a password |
| GET | `/api/accounts/users/` | No | 200 | User list |
| GET | `/api/accounts/users/<user-id>/` | No | 200 | Includes `comment_count` |
| POST | `/api/workspaces/` | Basic | 201 | Caller becomes owner and admin |
| GET | `/api/workspaces/<workspace-id>/` | Basic | 200 | Members only; others get 404 |
| GET | `/api/workspaces/<workspace-id>/members/` | Basic | 200 | |
| POST | `/api/workspaces/<workspace-id>/members/` | Basic | 201 | Admin only. Body: `user`, `role` |
| GET | `/api/workspaces/<workspace-id>/summary/` | Basic | 200 | `document_count`, `member_count`, `total_comments` |
| GET | `/api/documents/` | Basic | 200 | Query: `workspace`, `status`, `search`, `tag` |
| POST | `/api/documents/` | Basic | 201 | Admin or editor. Writes version 1 |
| PUT | `/api/documents/<document-id>/` | Basic | 200 | Full replace. Writes the next version |
| GET | `/api/documents/<document-id>/versions/` | Basic | 200 | Ordered by `version_number` |
| GET | `/api/documents/<document-id>/stats/` | Basic | 200 | `version_count`, `contributor_count`, `comment_count` |
| GET | `/api/documents/<document-id>/tags/` | Basic | 200 | Tags on the document |
| POST | `/api/documents/<document-id>/tags/` | Basic | 200 | Admin or editor. Names and/or ids |
| GET | `/api/comments/comments/` | No | 200 | Query: `document`, `author`. Top-level rows include replies |
| POST | `/api/comments/comments/` | No | 201 | Body: `document`, `author`, `content`, optional `parent` |
| GET | `/api/comments/comments/<comment-id>/` | No | 200 | |
| GET | `/api/comments/tags/` | No | 200 | Query: `search` |
| POST | `/api/comments/tags/` | No | 201 | Body: `name` |
| GET | `/api/auditlogs/audit-logs/` | No | 200 | Also at `/api/auditlogs/auditlogs/` |
| GET | `/api/auditlogs/audit-logs/<audit-log-id>/` | No | 200 | |
| GET | `/api/auditlogs/audit-logs/summary/` | No | 200 | `total`, `created_count`, `updated_count` |

### Request and response fields

**Register user** `POST /api/accounts/users/`

| Field | Required | Rules |
| --- | --- | --- |
| `first_name` | Yes | Trimmed, not blank, max 50 |
| `last_name` | Yes | Trimmed, not blank, max 50 |
| `email` | Yes | Trimmed, lowercased, must contain `@`, unique |
| `phone` | Yes | Exactly 10 digits, unique |

Response adds `id`, `full_name`, `is_active`, `comment_count` on retrieve, `created_at`, and `updated_at`. Duplicate email or phone returns `400`.

**Workspace** `POST /api/workspaces/`

Body: `name` (required), optional `is_active` (default `true`). `owner` is the signed-in user. Response adds `id`, `owner`, `created_at`, and `member_count`.

**Add member** `POST /api/workspaces/<workspace-id>/members/`

| Field | Required | Rules |
| --- | --- | --- |
| `user` | Yes | Existing user UUID |
| `role` | Yes | `admin`, `editor`, or `viewer` |

Response: `id`, `workspace`, `user` (`id`, `first_name`, `last_name`, `email`), `role`, `joined_at`. A second membership for the same user returns `409`. A non-admin receives `403`.

**Document** `POST /api/documents/` and `PUT /api/documents/<document-id>/`

| Field | Required | Rules |
| --- | --- | --- |
| `title` | Yes | Non-blank string, max 255 |
| `content` | Yes | String. Whitespace is kept |
| `workspace` | Yes | Workspace UUID. Cannot be changed on update |
| `status` | Yes | `draft`, `published`, or `archived` |

Response adds `id`, `created_by`, `created_at`, `updated_at`, and `version_count`. `created_by` stays the original creator. A viewer receives `403`. A version-number clash returns `409`.

**Versions** each item is `id`, `document`, `content`, `version_number`, `saved_by` (`id`, `first_name`, `last_name`, `email`), `saved_at`.

**Attach tags** `POST /api/documents/<document-id>/tags/`

| Field | Required | Rules |
| --- | --- | --- |
| `tags` | Yes | Non-empty list of names or existing tag UUIDs |
| `tag_ids` | No | Extra existing tag UUIDs |

Unknown UUIDs return `400`. A name that is not a UUID is lowercased and created when missing. Response: `tags` (ids) and `tag_names`.

**Comment** `POST /api/comments/comments/`

| Field | Required | Rules |
| --- | --- | --- |
| `document` | Yes | Document UUID |
| `author` | No | User UUID. Omitted or null leaves the author empty |
| `content` | Yes | Trimmed, not blank |
| `parent` | No | Comment UUID on the same document |

List query `document` and `author` filter rows. List results are top-level comments with `reply_count` and `replies`.

**Tag** `POST /api/comments/tags/`

Body: `name`. Stored trimmed and lowercased. Response: `id`, `name`, `documents`, `document_count`, `created_at`. A name that already exists returns `400`. `GET /api/comments/tags/?search=` matches part of the name.

**Audit log** items are `id`, `actor`, `action` (`created` or `updated`), `model_name`, `object_id`, `timestamp`. Document saves write these rows. List filters: `model_name`, `actor` or `actor_id`, `start` or `start_date`, `end` or `end_date`. Creating a log through the API returns `405`.
