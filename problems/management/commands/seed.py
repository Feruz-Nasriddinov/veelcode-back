import os
import random
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.models import Comment, Like, Problem, ProblemFile
from users.models import Submission, User, UserLocation

TIMEZONES = [
    'UTC', 'Asia/Tokyo', 'Asia/Tashkent', 'Europe/Berlin', 'Europe/London',
    'America/New_York', 'America/Los_Angeles', 'Australia/Sydney',
]

USERNAMES = [
    'alice', 'bob', 'carol', 'dave', 'erin', 'frank', 'grace', 'heidi', 'ivan', 'judy',
]

PROBLEMS = [
    {
        'title': 'Login endpoint returns 500 on wrong password',
        'description': 'The login view crashes instead of returning 401 when the password is wrong. Fix it so bad credentials get a clean error.',
        'difficulty': 'easy', 'field': 'backend', 'language': 'python', 'framework': 'django rest framework',
        'files': {
            'README.md': '# Auth service\n\nLogin returns 500 on a wrong password. Make it return 401.\n',
            'requirements.txt': 'Django>=5.0\ndjangorestframework>=3.15\n',
            'accounts/views.py': 'from django.contrib.auth import authenticate\nfrom rest_framework.response import Response\nfrom rest_framework.views import APIView\n\n\nclass LoginView(APIView):\n    def post(self, request):\n        user = authenticate(username=request.data["username"], password=request.data["password"])\n        return Response({"id": user.id})\n',
        },
        'hidden': {
            'tests/test_hidden_login.py': 'def test_wrong_password_returns_401(client):\n    response = client.post("/login/", {"username": "a", "password": "b"})\n    assert response.status_code == 401\n',
        },
    },
    {
        'title': 'Add soft delete to the notes model',
        'description': 'Deleting a note should hide it instead of removing the row. Deleted notes must not show up in the list endpoint.',
        'difficulty': 'medium', 'field': 'backend', 'language': 'python', 'framework': 'django',
        'files': {
            'README.md': '# Notes\n\nAdd soft delete: set `deleted_at` instead of deleting rows.\n',
            'requirements.txt': 'Django>=5.0\n',
            'notes/models.py': 'from django.db import models\n\n\nclass Note(models.Model):\n    body = models.TextField()\n    created_at = models.DateTimeField(auto_now_add=True)\n',
        },
        'hidden': {
            'tests/test_hidden_soft_delete.py': 'def test_deleted_note_hidden_from_list(client):\n    assert True\n',
        },
    },
    {
        'title': 'Race condition in inventory reservation',
        'description': 'Two concurrent orders can reserve the same last item. Make reservation safe under concurrency without locking the whole table.',
        'difficulty': 'hard', 'field': 'backend', 'language': 'python', 'framework': 'django rest framework',
        'files': {
            'README.md': '# Inventory\n\nConcurrent reservations oversell stock. Fix it.\n',
            'requirements.txt': 'Django>=5.0\ndjangorestframework>=3.15\n',
            'inventory/services.py': 'from .models import Item\n\n\ndef reserve(item_id, qty):\n    item = Item.objects.get(pk=item_id)\n    if item.stock >= qty:\n        item.stock -= qty\n        item.save()\n        return True\n    return False\n',
        },
        'hidden': {
            'tests/test_hidden_reserve.py': 'def test_no_oversell():\n    assert True\n',
            'tests/test_hidden_reserve_edge.py': 'def test_zero_qty_rejected():\n    assert True\n',
        },
    },
    {
        'title': 'Todo list re-renders on every keystroke',
        'description': 'Typing in the search box re-renders every todo item. Stop the extra renders without changing what the list shows.',
        'difficulty': 'medium', 'field': 'frontend', 'language': 'javascript', 'framework': 'react',
        'files': {
            'README.md': '# Todo app\n\nEvery keystroke re-renders all items. Fix it.\n',
            'package.json': '{\n  "name": "todo-app",\n  "private": true,\n  "dependencies": {"react": "^18.3.0", "react-dom": "^18.3.0"}\n}\n',
            'src/TodoList.jsx': 'export default function TodoList({ todos, query }) {\n  return todos\n    .filter((t) => t.title.includes(query))\n    .map((t) => <TodoItem key={t.id} todo={t} onToggle={() => {}} />);\n}\n',
        },
        'hidden': {
            'tests/hidden/TodoList.test.jsx': 'test("filters todos", () => {\n  expect(true).toBe(true);\n});\n',
        },
    },
    {
        'title': 'Form submits twice on double click',
        'description': 'Users can double click Save and create two records. Disable the button while the request is in flight.',
        'difficulty': 'easy', 'field': 'frontend', 'language': 'typescript', 'framework': 'react',
        'files': {
            'README.md': '# Profile form\n\nDouble clicking Save sends two requests.\n',
            'package.json': '{\n  "name": "profile-form",\n  "private": true,\n  "dependencies": {"react": "^18.3.0", "react-dom": "^18.3.0"}\n}\n',
            'src/ProfileForm.tsx': 'export function ProfileForm({ onSave }: { onSave: () => Promise<void> }) {\n  return <button onClick={() => onSave()}>Save</button>;\n}\n',
        },
        'hidden': {
            'tests/hidden/ProfileForm.test.tsx': 'test("button disabled while saving", () => {\n  expect(true).toBe(true);\n});\n',
        },
    },
    {
        'title': 'Product page is not statically generated',
        'description': 'The product page fetches data on every request. Make it static with revalidation every 60 seconds.',
        'difficulty': 'hard', 'field': 'frontend', 'language': 'typescript', 'framework': 'next.js',
        'files': {
            'README.md': '# Shop\n\nProduct pages should be static with 60s revalidation.\n',
            'package.json': '{\n  "name": "shop",\n  "private": true,\n  "dependencies": {"next": "^15.0.0", "react": "^19.0.0", "react-dom": "^19.0.0"}\n}\n',
            'app/products/[id]/page.tsx': 'export const dynamic = "force-dynamic";\n\nexport default async function Page({ params }: { params: { id: string } }) {\n  const res = await fetch(`https://api.example.com/products/${params.id}`, { cache: "no-store" });\n  const product = await res.json();\n  return <h1>{product.name}</h1>;\n}\n',
        },
        'hidden': {
            'tests/hidden/page.test.ts': 'test("page is static", () => {\n  expect(true).toBe(true);\n});\n',
        },
    },
    {
        'title': 'Dockerfile runs the app as root',
        'description': 'The production image runs as root and ships build tools. Use a non-root user and a multi-stage build.',
        'difficulty': 'easy', 'field': 'devops', 'language': 'python', 'framework': 'django',
        'files': {
            'README.md': '# API image\n\nHarden the Dockerfile.\n',
            'Dockerfile': 'FROM python:3.12\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nCMD ["gunicorn", "config.wsgi"]\n',
        },
        'hidden': {
            'tests/test_hidden_dockerfile.py': 'def test_non_root_user():\n    assert True\n',
        },
    },
    {
        'title': 'CI pipeline never caches dependencies',
        'description': 'Every CI run reinstalls all packages and takes 6 minutes. Add dependency caching keyed on the lock file.',
        'difficulty': 'medium', 'field': 'devops', 'language': 'javascript', 'framework': 'next.js',
        'files': {
            'README.md': '# CI\n\nAdd dependency caching to the workflow.\n',
            '.github/workflows/ci.yml': 'name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: npm install\n      - run: npm test\n',
        },
        'hidden': {
            'tests/test_hidden_ci.py': 'def test_cache_step_present():\n    assert True\n',
        },
    },
    {
        'title': 'Compose stack starts the app before the database',
        'description': 'The app container crashes on boot because Postgres is not ready yet. Add a healthcheck and wait on it.',
        'difficulty': 'medium', 'field': 'devops', 'language': 'python', 'framework': 'django',
        'files': {
            'README.md': '# Stack\n\nThe app starts before the database is ready.\n',
            'docker-compose.yml': 'services:\n  db:\n    image: postgres:16\n  app:\n    build: .\n    depends_on:\n      - db\n',
        },
        'hidden': {
            'tests/test_hidden_compose.py': 'def test_db_healthcheck():\n    assert True\n',
        },
    },
]

COMMENTS = [
    'Took me a while to find the root cause, nice one.',
    'Is the README hint enough? I got stuck for an hour.',
    'Hidden tests are strict about edge cases, read the description carefully.',
    'This is exactly the bug we had in production last month.',
    'Solved it, but my first attempt broke another endpoint.',
    'Good practice for interviews.',
    'Would love a follow-up problem on this topic.',
    'The difficulty label feels right.',
]


class Command(BaseCommand):
    help = 'Fill the database with dummy users, problems, comments, likes and submissions. Safe to run more than once.'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Refusing to seed: DEBUG is off.')
        password = os.environ.get('SEED_PASSWORD')
        if not password:
            raise CommandError('Set SEED_PASSWORD to the password the seed users should get.')

        rng = random.Random(42)
        with transaction.atomic():
            users = self.seed_users(rng, password)
            problems = self.seed_problems(users)
            self.seed_comments(rng, users, problems)
            self.seed_submissions(rng, users, Problem.objects.filter(status='accepted'))

        self.stdout.write(self.style.SUCCESS(
            f'Done. users={User.objects.count()} problems={Problem.objects.count()} '
            f'files={ProblemFile.objects.count()} comments={Comment.objects.count()} '
            f'likes={Like.objects.count()} submissions={Submission.objects.count()}'
        ))

    def seed_users(self, rng, password):
        users = []
        for name in USERNAMES:
            user = User.objects.filter(username=name).first()
            if user is None:
                user = User.objects.create_user(username=name, email=f'{name}@example.com', password=password)
                UserLocation.objects.create(user=user, timezone=rng.choice(TIMEZONES))
            users.append(user)
        return users

    def seed_problems(self, users):
        problems = []
        for i, spec in enumerate(PROBLEMS):
            data = {k: v for k, v in spec.items() if k not in ('files', 'hidden')}
            problem = Problem.objects.filter(title=data['title']).first()
            if problem is None:
                status = 'pending' if i == len(PROBLEMS) - 1 else 'accepted'
                problem = Problem.objects.create(
                    **data, status=status, created_by=users[i % len(users)],
                    time_required={'easy': 30, 'medium': 60, 'hard': 120}[data['difficulty']],
                )
                ProblemFile.objects.bulk_create(
                    [ProblemFile(problem=problem, directory=d, content=c) for d, c in spec['files'].items()]
                    + [ProblemFile(problem=problem, directory=d, content=c, is_hidden=True) for d, c in spec['hidden'].items()]
                )
            problems.append(problem)
        return problems

    def seed_comments(self, rng, users, problems):
        for problem in problems:
            if problem.comments.filter(user__in=users).exists():
                continue
            for author in rng.sample(users, rng.randint(1, 4)):
                comment = Comment.objects.create(user=author, problem=problem, text=rng.choice(COMMENTS))
                likers = rng.sample([u for u in users if u != author], rng.randint(0, 5))
                Like.objects.bulk_create([Like(user=u, comment=comment) for u in likers])
                comment.like_count = len(likers)
                comment.save(update_fields=['like_count'])

    def seed_submissions(self, rng, users, problems):
        problems = list(problems)
        now = timezone.now()
        for user in users:
            if user.submissions.exists():
                continue
            for _ in range(rng.randint(5, 30)):
                status = rng.choices(['done', 'failed', 'pending'], weights=[80, 15, 5])[0]
                submission = Submission.objects.create(
                    user=user,
                    problem=rng.choice(problems),
                    status=status,
                    score=rng.choice([0, 25, 50, 75, 100]) if status == 'done' else 0,
                    error_message='Container timed out' if status == 'failed' else None,
                )
                created_at = now - timedelta(days=rng.randint(0, 364), hours=rng.randint(0, 23))
                Submission.objects.filter(pk=submission.pk).update(created_at=created_at)
