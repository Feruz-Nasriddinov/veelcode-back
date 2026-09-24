# Veelcode Backend

> A platform where developers get real, broken or incomplete codebases and must fix bugs or add features — simulating actual company work instead of algorithmic puzzles.

## Overview

Veelcode is a code challenge platform that evaluates developers on practical engineering skills: reading unfamiliar code, debugging, refactoring, and extending existing systems. Challenges are grouped by domain (backend, frontend, DevOps) rather than by programming language.

This repository contains the **Django REST API backend** with JWT authentication (in progress), Docker-based code evaluation, and Celery for asynchronous task processing.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | Django 6.1 + Django REST Framework 3.18 |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Auth | JWT via `djangorestframework-simplejwt` (HttpOnly, SameSite=Lax cookies — **WIP**) |
| Task Queue | Celery + Redis |
| Code Execution | Docker containers (isolated, resource-limited) |
| Testing | pytest + pytest-django |

---

## Project Structure

```
corporate-prep/
├── config/                 # Django project settings, URLs, WSGI/ASGI
├── users/                  # User profiles, submission history
├── problems/               # Problem CRUD, submission handling, evaluation
├── uploader/               # Problem upload endpoints (authoring)
├── manage.py
├── requirements.txt
└── db.sqlite3              # Dev database
```

### Apps

| App | Responsibility |
|-----|----------------|
| `users` | UserDetail model linking users to problem attempts, scores, status |
| `problems` | Problem/ProblemFile models, listing, detail, submission, scoring endpoints |
| `uploader` | Authenticated problem creation and file upload (author workflow) |
| `config` | Project settings, routing, middleware |

---

## API Endpoints

All endpoints require authentication (`IsAuthenticated`).

### Problems

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/problems/` | List accepted problems (paginated, throttled: 20/min) |
| `GET` | `/api/problems/<uuid>/` | Get problem with files (throttled: 20/min) |
| `GET` | `/api/problems/<uuid>/history/` | User's submission history for a problem (throttled: 20/min) |
| `POST` | `/api/problems/<uuid>/submit/` | Submit solution files (throttled: 10/min) → returns `submission_id` |
| `GET` | `/api/problems/<uuid>/score/` | Get submission details by ID (throttled: 20/min) |

### Problem Authoring (Uploader)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload/problem/` | Create new problem (status=`pending`) |
| `POST` | `/api/upload/problem/<uuid>/` | Upload file to owned problem |

> **Note:** Uploader routes are not yet wired in `config/urls.py` — add `path('api/upload/', include('uploader.urls'))` to enable.

---

## Authentication (Work in Progress)

- **JWT** via `djangorestframework-simplejwt`
- Tokens stored in **HttpOnly, SameSite=Lax cookies** (not localStorage)
- Access + Refresh token rotation planned
- Current `REST_FRAMEWORK` config includes `JWTAuthentication` + `SessionAuthentication`
- Login/refresh/logout views **not yet implemented**

---

## Code Evaluation Pipeline

1. User submits solution files via `POST /api/problems/<uuid>/submit/`
2. Creates `UserDetail` record with `status=pending`
3. Celery task `evaluate_tasks` dispatched with submission ID + files
4. Task picks an evaluator by the problem's `field` + `framework` (`problems/services/evaluators/`):
   - **Backend (Django / DRF):** the user's app runs in one container (`django-evaluator`), and the hidden tests run in a second container (`veelcode-backend-grader`). The tests make HTTP calls to the app over a private network with no internet.
   - **Frontend (React, Next.js):** the app is built and served in `veelcode-frontend-runner`, and the hidden Playwright tests drive a browser against it from `veelcode-frontend-grader`.
   - **DevOps:** there's no runner. The hidden tests read the submission, mounted read-only at `/submission`, in `veelcode-devops-grader`.
   - Hidden tests (`ProblemFile.is_hidden=True`) never share a container with user code. Every container has memory, pid and time limits.
5. Parses JUnit XML → calculates pass percentage
6. Updates `UserDetail` with `score`, `status=done` (or `failed` on error/timeout)

### Security Model

- All user code runs in **ephemeral Docker containers**
- No network access, strict resource quotas
- Container removed after execution (success or failure)
- Host filesystem never exposed

---

## Getting Started

### Prerequisites

- Python 3.12+
- Redis (for Celery)
- Docker (for code evaluation)

### Installation

```bash
# Clone and enter
cd corporate-prep

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Environment variables
cp .env.example .env  # Create this file with SECRET_KEY, etc.

# Database
python manage.py migrate

# Run development server
python manage.py runserver
```

### Running Celery Worker

```bash
# Terminal 1: Redis (if not running as service)
redis-server

# Terminal 2: Celery worker
celery -A config worker -l info

# Terminal 3: Celery beat (removes leftover evaluator containers every 5 minutes)
celery -A config beat -l info
```

### Docker Evaluator Images

Build once:

```bash
docker build -t django-evaluator -f Dockerfile.evaluator .
for image in backend-grader frontend-runner frontend-grader devops-grader; do
  docker build -t veelcode-$image -f evaluators/$image.Dockerfile evaluators
done
```

### Writing hidden tests

Hidden tests are pytest files. The grader plugin (`evaluators/veelcode_grader.py`) provides these fixtures:

| Field | Fixture | What it is |
|-------|---------|------------|
| Backend | `client` | A `requests` session. Paths like `client.get("/api/x/")` go to the app, sent with `Host: localhost`. |
| Backend / Frontend | `app_url` | The app's base URL |
| Frontend | `page` | A Playwright page. `page.goto("/")` opens the app. |
| DevOps | `submission_dir` | A read-only `Path` to the submitted files |

- Django projects must have `manage.py` at the root and must accept `localhost` as a host.
- Frontend apps can only use the packages pre-installed in `evaluators/frontend-runner.Dockerfile`.
- `time_required` has to cover the app starting up or building, as well as the tests.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Django secret key |
| `DEBUG` | No | `True`/`False` (default: `True`) |
| `ALLOWED_HOSTS` | No | Comma-separated hosts (prod) |
| `DATABASE_URL` | No | Postgres URL (prod), defaults to SQLite |
| `REDIS_URL` | No | Celery broker (default: `redis://localhost:6379/0`) |
| `CORS_ALLOWED_ORIGINS` | No | Frontend origins for CORS |

---

## Throttling Configuration

Defined in `config/settings.py` under `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`:

| Scope | Rate |
|-------|------|
| `send-problems` | 20/min |
| `send-content` | 20/min |
| `send-score` | 20/min |
| `submit` | 10/min |
| `submit-details` | 20/min |
| `upload-problem` | 3/min |

Customize per-endpoint via `throttle_scope` on views.

---

## Data Models

### Problem
- `id` (UUID), `title`, `description`, `difficulty` (easy/medium/hard)
- `time_required` (seconds, default 120), `status` (pending/accepted/rejected)
- `created_by` (FK to User, `PROTECT` — author cannot be deleted)

### ProblemFile
- `problem` (FK), `directory` (path), `content` (source code/text)

### UserDetail (Submission)
- `user` (FK), `problem` (FK), `score` (0–100)
- `status` (pending/running/done/failed), `error_message`

---

## Development Notes

### Adding a New Endpoint
1. Create serializer in app's `serializers.py`
2. Add view in `views.py` (thin — delegate to service functions)
3. Register URL in app's `urls.py`
4. Include app URLs in `config/urls.py`
5. Write tests (success + failure cases)

### Database Changes
```bash
python manage.py makemigrations
python manage.py migrate
```
Never edit applied migrations — create new ones.

### Running Tests
```bash
pytest                    # All tests
pytest users/tests.py     # Single app
pytest -k "test_submit"   # Pattern match
```

---

## Roadmap / Known Gaps

- [ ] Complete JWT auth: login, refresh, logout, registration endpoints
- [ ] Wire uploader URLs in `config/urls.py`
- [ ] Add PostgreSQL production settings
- [ ] Implement problem review/approval workflow (pending → accepted/rejected)
- [ ] Add pagination to problem list
- [ ] Docker Compose for local dev (Django + Redis + Postgres + Celery)
- [ ] CI/CD pipeline
- [ ] API documentation (drf-spectacular / Swagger)

---

## License

Proprietary — internal use only.