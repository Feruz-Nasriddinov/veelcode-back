# Veelcode

Platform where users get a real, broken or incomplete codebase and must fix a bug or add a feature. It simulates actual company work instead of LeetCode-style puzzles. Challenges are grouped by domain (backend, frontend, DevOps), not by programming language.

## Communication rules (highest priority)

- Lead with the answer or the result. No preamble. Don't repeat my question back.
- No filler: no "Great question", "Certainly", "I'll now...", no apologies, no praise.
- After finishing a task, reply in 3 lines max: what changed, what to check, what's risky. The diff shows the rest.
- Don't explain code I can read. Explain only *why* when the reason isn't obvious.
- Plain English. If a simple word works, use it. If you must use a technical term, define it in one short clause.
- Be blunt. If my idea is bad, say so, give the reason in 1-2 sentences, and offer the better option. Don't hedge.
- If you're not sure, say "not sure" and say how to check. Never guess about APIs, versions, or behavior.
- Ask a question only when blocked, and ask one. Otherwise pick the most reasonable option, state the assumption in one line, and continue.
- Exception: if I say "explain", "teach me", or "why", give a full plain-English explanation, including what the syntax means and why the logic works. Otherwise stay short.

## Stack

- Backend: Python, Django, Django REST Framework
- Database: <FILL IN>
- Frontend: <FILL IN>
- Infra / deploy: <FILL IN>

## Commands

<!-- Fill in the real ones. Claude can't guess these. -->
- Run server: `<FILL IN>`
- Run tests: `<FILL IN>`  (single test: `<FILL IN>`)
- Lint / format: `<FILL IN>`
- Migrations: `python manage.py makemigrations && python manage.py migrate`

## How to work

- One problem at a time. Small, focused changes. Don't refactor code I didn't mention. Don't add features I didn't ask for.
- Read the existing code first and match its patterns before writing new ones.
- For anything touching more than 3 files or the database schema: show a short plan and wait for my OK.
- Run tests and lint before saying "done". If you couldn't run them, say so. Never claim something works without verifying it.
- Don't commit unless I ask.
- Don't write comments.

## Backend conventions

<!-- Edit these to match what the repo actually does. Delete what's wrong. -->
- Keep views thin. Business logic goes in service functions, not in views or serializers.
- Validate all input in serializers.
- Avoid N+1 queries: use `select_related` / `prefetch_related` when following relations.
- Never edit a migration that has already been applied. Create a new one.
- Every new endpoint gets at least one test for the success case and one for a failure case.
- Config and secrets come from environment variables. Never hardcode them.

## Security (this product runs other people's code)

- Treat all user-submitted code as untrusted.
- Any code execution must be sandboxed with time, memory, and network limits. Never run submissions directly on the app server.
- Grading: each problem has hidden test files (`ProblemFile.is_hidden=True`) that are never sent to users. On submit, only the hidden tests count; the score is passed / total × 100. The user's own tests never count.
- Evaluators live in `problems/services/evaluators/`, one per field, picked by `field` + `framework`. Hidden tests must never run in the same container or process as user code: backend/frontend tests reach the app over a private no-internet network; DevOps tests only read the submission (read-only mount), never run it.
- Evaluator images are built from `Dockerfile.evaluator` and `evaluators/*.Dockerfile`.
- Ask me before changing how grading works.

## Never do without asking

- Add or upgrade dependencies
- Touch `.env` files or credentials
- Run destructive commands (dropping tables, deleting data, force-pushing)
- Change the public API shape or database schema