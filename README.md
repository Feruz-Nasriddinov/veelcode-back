# Veelcode Backend

> A platform where developers get real, broken or incomplete codebases and must fix bugs or add features — simulating actual company work instead of algorithmic puzzles.

## Overview

Veelcode tests practical engineering skills: reading code you didn't write, debugging, and extending an existing system. Challenges are grouped by domain (backend, frontend, DevOps), not by programming language.

This repository is the **Django REST API backend**. It handles cookie-based JWT auth, problems and comments, problem authoring, and grading submissions in isolated Docker containers through Celery.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | Django 6.1 + Django REST Framework 3.18 |
| Database | PostgreSQL via `DATABASE_URL`; falls back to SQLite when unset |
| Auth | `djangorestframework-simplejwt`, tokens in HttpOnly cookies, CSRF-protected |
| Task queue | Celery + Redis (worker for grading, beat for cleanup) |
| Code execution | Docker containers with memory, process-count and time limits |
| Serving | gunicorn + WhiteNoise (static files) |
| Tests / CI | Django test runner (`manage.py test`), GitHub Actions |

---

## Project Structure

```
corporate-prep/
├── config/                  # Settings, root URLs, Celery app, WSGI/ASGI
├── authentication/          # Signup, login, refresh, logout, CSRF; cookie JWT auth class
├── users/                   # Custom User, Submission, UserLocation; profile + activity
├── problems/                # Problems, comments, likes, submitting, grading
│   ├── services/evaluators/ # One evaluator per field (backend / frontend / devops)
│   └── management/commands/seed.py
├── uploader/                # Problem authoring endpoints (no models of its own)
├── evaluators/              # Dockerfiles + pytest plugin for the grading images
├── Dockerfile.evaluator     # Image that runs submitted Django apps
├── build.sh                 # Deploy build: install, collectstatic, migrate
├── .github/workflows/django.yml
└── requirements.txt
```

---

## API Endpoints

Every endpoint needs a logged-in user unless marked **public**. Rate limits come from `throttle_scope` on each view (see [Throttling](#throttling)).

### Auth — `/api/auth/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/auth/csrf/` | **Public.** Sets the `csrftoken` cookie. Call this first. |
| `POST` | `/api/auth/signup/` | **Public.** `username`, `email`, `password`, `password_confirmation`, optional `timezone` (default `UTC`). Sets auth cookies. |
| `POST` | `/api/auth/login/` | **Public.** `identifier` (username or email) + `password`. Sets auth cookies. |
| `POST` | `/api/auth/google/` | **Public.** `code` from Google's redirect. Creates or links an account and sets auth cookies. |
| `POST` | `/api/auth/github/` | **Public.** `code` from GitHub's redirect. Creates or links an account and sets auth cookies. |
| `POST` | `/api/auth/refresh/` | **Public.** Uses the refresh cookie to issue new tokens; the old refresh token is blacklisted. |
| `POST` | `/api/auth/logout/` | **Public.** Blacklists the refresh token and clears both cookies. |
| `GET` | `/api/auth/me/` | Current user (`id`, `username`, `email`). |

### Problems and submissions — `/api/problems/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/problems/` | Accepted problems, most-submitted first. Paginated (20 per page). |
| `GET` | `/api/problems/<problem_id>/` | Problem with its visible files and `comment_count`. Hidden test files are never returned. |
| `POST` | `/api/problems/<problem_id>/submit/` | Body is a JSON object mapping file paths to file contents. Returns `202` with `submission_id`. Returns `503` if the queue is down. |
| `GET` | `/api/problems/<submission_id>/score/` | Status and score of one of your submissions. Note: takes a **submission** id, not a problem id. |
| `GET` | `/api/problems/history/` | All your submissions, newest first. |

Submission limits (`config/settings.py`): at most 200 files, paths up to 255 characters, 1 MB total. Paths must be relative, use `/`, and can't contain `..` or `:`.

### Comments and likes

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/problems/<problem_id>/comments/` | Paginated comments, each with `like_count` and `liked_by_me`. |
| `POST` | `/api/problems/<problem_id>/comments/` | Add a comment (`text`, up to 1000 characters). |
| `PATCH` | `/api/comments/<comment_id>/edit/` | Edit your own comment. |
| `DELETE` | `/api/comments/<comment_id>/delete/` | Delete your own comment. |
| `POST` | `/api/comments/<comment_id>/like/` | Like a comment. Liking twice has no extra effect. |
| `DELETE` | `/api/comments/<comment_id>/unlike/` | Remove your like. |

### Users — `/api/users/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/users/profile/` | Your submissions with language, framework, difficulty and score. |
| `GET` | `/api/users/profile/activity/?year=YYYY` | Submissions per day for a year, counted in your timezone. `year` runs from 2026 to the current year. |

### Problem authoring — `/api/uploader/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/uploader/problem/` | Create a problem (`title`, `description`, `difficulty`, `field`, `language`, `framework`, `source`). It starts as `pending`. |
| `POST` | `/api/uploader/problem/<problem_id>/content/` | Add files to your own pending problem in one request: `{"<path>": {"content": "...", "is_hidden": false}}`. All or nothing. Returns `[{id, directory, is_hidden}]`. |
| `POST` | `/api/uploader/content/<problem_file_id>/update/` | Propose new content for a file in your problem. Saved as an `UpdateProblem` record; the file itself isn't changed. |

`source` is optional and says where the codebase came from: either the URL of the public GitHub repo it was taken from, or, if the repo is private, a short description of that repo.

A path can be stored once per problem, and a file can't share its path with a folder (`a.py` and `a.py/b.py`). Uploading a path that's already stored is rejected; change it through the update endpoint.

Problems are accepted or rejected by changing `status` in the Django admin (`/admin/`). Set `time_required` there too: the upload API doesn't accept it and the default is `0`.

---

## Authentication

- Tokens live in **HttpOnly cookies**, never in the response body:
  - `access_token` — path `/`, valid 10 minutes.
  - `refresh_token` — path `/api/auth/` only, valid 14 days. It is replaced on every refresh and the old one is blacklisted.
- Cookies use `SameSite=Lax`, and are HTTPS-only (`Secure`) unless `DEBUG=True`.
- **CSRF:** every non-GET request, including login and signup, must send the `csrftoken` cookie value in an `X-CSRFToken` header. Get the cookie from `GET /api/auth/csrf/`.
- JWTs are signed with `JWT_SIGNING_KEY`, kept separate from `SECRET_KEY` so either can be rotated without breaking the other.
- The user model is `users.User` (`AUTH_USER_MODEL`). Usernames and emails are unique regardless of case, and usernames can't contain `@`.

---

## Code Evaluation Pipeline

1. `POST /api/problems/<id>/submit/` validates the files, creates a `Submission` with `status=pending`, queues the Celery task `evaluate_tasks`, and increases the problem's `submission_count`.
2. The task picks an evaluator by the problem's `field` + `framework` (`problems/services/evaluators/__init__.py`):
   - **Backend (Django / DRF):** the user's app runs in a `django-evaluator` container (`migrate`, then `runserver`). The hidden tests run in a separate `veelcode-backend-grader` container and call the app over HTTP.
   - **Frontend (React / Next.js):** the app is built and served in `veelcode-frontend-runner` (Vite build, or `next build` + `next start`). Hidden Playwright tests run from `veelcode-frontend-grader`.
   - **DevOps:** there is no runner. The hidden tests in `veelcode-devops-grader` only read the submission, mounted read-only at `/submission`.
   - Any other field/framework pair fails with "Unsupported problem type".
3. Only hidden files (`ProblemFile.is_hidden=True`) ending in `.py` are run as tests. `conftest.py` is copied but not passed to pytest. The user's own tests never count.
4. The grader writes a JUnit XML report. Score = passed / total × 100, rounded. Failures, errors and skips all count as not passed.
5. The `Submission` becomes `done` with a score, or `failed` with an `error_message` (timeout, out of memory, app did not start, no hidden tests, internal error).

### Isolation and limits

- Hidden tests never run in the same container or process as user code.
- Backend and frontend: runner and grader share a private Docker network created for that run with `internal=True` (no internet access). DevOps graders run with no network.
- Default limits per container: 512 MB memory, 128 processes. Frontend containers get 1 GB / 256; the DevOps grader gets 256 MB.
- Time: the containers get `time_required + 5` seconds. The Celery task has a soft limit of `time_required + 10` and a hard limit of `+ 20`.
- Docker errors (daemon down, etc.) retry up to 5 times, then the submission fails with "Infra error after retries".
- Every container and network is removed after the run. Each one is also labeled with an expiry time, and Celery beat runs `cleanup_evaluator_leftovers` every 5 minutes to remove any left behind.

---

## Getting Started

### Prerequisites

- Python 3.14 (what CI uses)
- Redis (Celery broker)
- Docker (only needed to actually grade submissions)

### Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then fill in SECRET_KEY and JWT_SIGNING_KEY
python manage.py migrate
python manage.py runserver
```

### Celery

```bash
redis-server                          # if Redis isn't already running
celery -A config worker -l info       # runs grading tasks
celery -A config beat -l info         # removes leftover evaluator containers every 5 min
```

To skip Redis and the worker during local work, set `CELERY_TASK_ALWAYS_EAGER=True`. Tasks then run inside the request.

### Evaluator images

Build these once on the machine running the Celery worker:

```bash
docker build -t django-evaluator -f Dockerfile.evaluator .
for image in backend-grader frontend-runner frontend-grader devops-grader; do
  docker build -t veelcode-$image -f evaluators/$image.Dockerfile evaluators
done
```

### Seed data

```bash
SEED_PASSWORD=<password> python manage.py seed
```

Creates 10 users (`alice`, `bob`, … with emails `<name>@example.com`, all using `SEED_PASSWORD`), sample problems for every field with hidden tests, plus GitHub/Google social accounts for every other user, README update requests, comments, likes and a year of submissions. Only runs when `DEBUG=True`. Safe to run more than once: existing users aren't duplicated, and problem files are rebuilt from the seed file.

---

## Writing hidden tests

Hidden tests are pytest files. The grader plugin (`evaluators/veelcode_grader.py`) provides these fixtures:

| Field | Fixture | What it is |
|-------|---------|------------|
| Backend | `client` | A `requests` session. Paths like `client.get("/api/x/")` go to the app, sent with `Host: localhost`. |
| Backend / Frontend | `app_url` | The app's base URL |
| Frontend | `page` | A Playwright page. `page.goto("/")` opens the app. |
| DevOps | `submission_dir` | A read-only `Path` to the submitted files |

- Django projects must have `manage.py` at the root and must accept `localhost` as a host.
- Before running tests, the plugin waits up to `time_required` seconds for the app to respond. If it never does, the submission fails with "App did not start".
- Frontend apps can only use the packages pre-installed in `evaluators/frontend-runner.Dockerfile` (React 19, Vite 8, Next.js 16, TypeScript 5).
- DevOps tests have `pyyaml` available.
- `time_required` has to cover the app starting up or building, as well as the tests.

---

## Environment Variables

See `.env.example`. Origins must include the scheme (`https://...`), or Django refuses to start.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | insecure dev key, only when `DEBUG=True` | **Required when `DEBUG=False`**, or Django refuses to start. |
| `JWT_SIGNING_KEY` | insecure dev key, only when `DEBUG=True` | **Required when `DEBUG=False`**, or Django refuses to start. Signs JWTs. |
| `DEBUG` | `False` | Set `True` for local dev. Also turns off the HTTP-to-HTTPS redirect and `Secure` cookies; with `False`, all HTTP requests are redirected. |
| `ALLOWED_HOSTS` | empty | Comma-separated. Required when `DEBUG=False`. |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | e.g. a Postgres URL in production. |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker. |
| `CELERY_BROKER_URL` | `REDIS_URL` | Overrides the broker. |
| `CELERY_RESULT_BACKEND` | none | Optional. |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | Run tasks inside the request instead of a worker. |
| `CORS_ALLOWED_ORIGINS` | empty | Comma-separated frontend origins. Credentials are allowed, so they must be exact. |
| `CSRF_TRUSTED_ORIGINS` | empty | Usually the same as `CORS_ALLOWED_ORIGINS`. |
| `SECURE_HSTS_SECONDS` | `3600` if `DEBUG` is off, else `0` | Tells browsers to use HTTPS only, for this many seconds. Raise to `31536000` once HTTPS is confirmed working. |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | on if `DEBUG` is off | Applies HSTS to subdomains too. |
| `SECURE_HSTS_PRELOAD` | `False` | Only for an owned domain you will submit to the browser preload list. Hard to undo. |
| `AUTH_COOKIE_DOMAIN` | none | Only for sharing cookies across subdomains. |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` | empty | Google sign-in. Scopes `openid email`. Unset means `/api/auth/google/` answers `400`. |
| `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`, `GITHUB_OAUTH_REDIRECT_URI` | empty | GitHub sign-in. Scopes `read:user user:email`. Unset means `/api/auth/github/` answers `400`. |
| `EMAIL_BACKEND` | console if `DEBUG`, else SMTP | |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | `587`, TLS on | SMTP settings. |
| `SEED_PASSWORD` | — | Only for `manage.py seed`. |

---

## Throttling

Defined in `config/settings.py` under `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`, applied per view with `throttle_scope`.

| Scope | Rate | Used by |
|-------|------|---------|
| `send-problems` | 20/min | Problem list |
| `send-content` | 20/min | Problem detail |
| `submit` | 3/min | Submit |
| `submit-details` | 40/min | Submission score |
| `history` | 20/min | Submission history |
| `comments-read` | 60/min | Reading comments |
| `comment` | 20/min | Creating, editing, deleting comments |
| `like` / `unlike` | 40/min | Likes |
| `profile` | 20/min | Profile |
| `activity-track` | 20/min | Activity |
| `upload-problem` | 3/min | Creating problems |
| `upload-files` | 10/min | Adding files to a problem |
| `update-problem` | 10/min | Proposing file updates |
| `auth-signup` | 10/hour | Signup |
| `auth-login` | 10/min | Login |
| `auth-refresh` | 20/min | Refresh |
| `auth-social` | 10/min | Google and GitHub sign-in |

`send-score` is defined but no view uses it.

---

## Data Models

**`users.User`** — extends `AbstractUser`. `username` and `email` are unique, case-insensitive.

**`users.UserLocation`** — one per user. `timezone` (default `UTC`), set at signup, used by the activity endpoint.

**`users.Submission`** — `id` (UUID), `user`, `problem`, `score` (0–100), `status` (`pending` / `done` / `failed`), `error_message`, `created_at`.

**`problems.Problem`** — `id` (UUID), `title`, `description`, `difficulty` (easy/medium/hard), `field` (backend/frontend/devops), `language`, `framework`, `source` (public GitHub repo URL, or a description of the private repo; max 255 characters), `time_required` (seconds, default 0), `status` (pending/accepted/rejected), `submission_count`, `created_by` (`PROTECT`: a user who created problems can't be deleted), `created_at`.

**`problems.ProblemFile`** — `id` (UUID), `problem`, `directory` (file path), `content`, `is_hidden` (hidden test files, never sent to users).

**`problems.UpdateProblem`** — a proposed change: `problem`, `problem_file`, `new_content`.

**`problems.Comment`** — `user` (kept as `null` if the user is deleted), `problem`, `text`, `like_count`, `created_at`.

**`problems.Like`** — `user`, `comment`, `created_at`. One like per user per comment.

---

## Development

### Tests

```bash
python manage.py test                                    # everything
python manage.py test problems                           # one app
python manage.py test problems.tests.test_views          # one module
RUN_DOCKER_TESTS=1 python manage.py test problems.tests.test_live_docker   # real containers
```

The live Docker tests are skipped unless `RUN_DOCKER_TESTS=1`. They need a running Docker daemon and the evaluator images.

Tests create a throwaway test database on whatever server `DATABASE_URL` points to. If your `.env` points at a remote Postgres, run with `DATABASE_URL=sqlite:///db.sqlite3` for a fast local run.

### CI

`.github/workflows/django.yml` runs on every push and pull request: `check`, `check --deploy`, a check that no migrations are missing, `migrate`, then the full test suite.

### Database changes

```bash
python manage.py makemigrations
python manage.py migrate
```

Never edit an applied migration — create a new one.

### Adding an endpoint

1. Validate input in a serializer.
2. Keep the view thin; put logic in a service function (see `authentication/services.py`, `problems/services/`).
3. Set a `throttle_scope` and add its rate to settings.
4. Register the URL in the app's `urls.py`.
5. Write tests for the success case and at least one failure case.

### Deploy

`build.sh` installs dependencies, runs `collectstatic` and applies migrations. Serve with `gunicorn config.wsgi`. Static files are served by WhiteNoise. The Celery worker needs Docker access and the evaluator images.

---

## License

Proprietary — internal use only.
