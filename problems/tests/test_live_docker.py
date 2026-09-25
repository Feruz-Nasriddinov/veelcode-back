import os
import unittest

from django.test import TestCase

from .base import ProblemsTestCase


def docker_tests_enabled():
    return os.environ.get('RUN_DOCKER_TESTS') == '1'


DOCKER_SKIP_REASON = 'Needs a Docker daemon and the evaluator images; set RUN_DOCKER_TESTS=1.'


class LiveDockerTestCase(ProblemsTestCase):
    def evaluate(self, files, hidden, time_required=60, **problem_fields):
        from problems.services.evaluators import evaluate

        problem = self.make_problem_with_hidden_tests(
            hidden, time_required=time_required, **problem_fields
        )
        return evaluate(files, problem.id)

    def leftovers(self):
        import docker

        client = docker.from_env()
        return (
            len(client.containers.list(all=True, filters={'name': 'veelcode-app-'})),
            len(client.networks.list(filters={'name': 'veelcode-'})),
        )


DJANGO_PROJECT = {
    'manage.py': (
        'import os, sys\n'
        'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop.settings")\n'
        'from django.core.management import execute_from_command_line\n'
        'execute_from_command_line(sys.argv)\n'
    ),
    'shop/__init__.py': '',
    'shop/settings.py': (
        'SECRET_KEY = "test"\n'
        'DEBUG = True\n'
        'ALLOWED_HOSTS = []\n'
        'ROOT_URLCONF = "shop.urls"\n'
        'INSTALLED_APPS = []\n'
        'DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"}}\n'
    ),
    'shop/urls.py': (
        'import socket\n'
        'from django.http import JsonResponse\n'
        'from django.urls import path\n'
        'from shop.pricing import add\n'
        'def add_view(request):\n'
        '    return JsonResponse({"result": add(int(request.GET["a"]), int(request.GET["b"]))})\n'
        'def online_view(request):\n'
        '    try:\n'
        '        socket.create_connection(("1.1.1.1", 80), timeout=3)\n'
        '        return JsonResponse({"online": True})\n'
        '    except OSError:\n'
        '        return JsonResponse({"online": False})\n'
        'urlpatterns = [path("add/", add_view), path("online/", online_view)]\n'
    ),
    'shop/pricing.py': 'def add(a, b):\n    return a + b\n',
}

DJANGO_HIDDEN_TESTS = {
    'test_add.py': (
        'def test_adds(client):\n'
        '    assert client.get("/add/?a=1&b=2").json() == {"result": 3}\n'
        'def test_adds_negatives(client):\n'
        '    assert client.get("/add/?a=-1&b=1").json() == {"result": 0}\n'
    ),
}

PYTEST_CHEAT = (
    'import _pytest.reports\n'
    '_original = _pytest.reports.TestReport.from_item_and_call.__func__\n'
    'def _always_pass(cls, item, call):\n'
    '    report = _original(cls, item, call)\n'
    '    report.outcome = "passed"\n'
    '    return report\n'
    '_pytest.reports.TestReport.from_item_and_call = classmethod(_always_pass)\n'
)


@unittest.skipUnless(docker_tests_enabled(), DOCKER_SKIP_REASON)
class BackendLiveDockerTests(LiveDockerTestCase):
    def evaluate_django(self, pricing=None, hidden=None, time_required=30, **extra_files):
        files = dict(DJANGO_PROJECT, **extra_files)
        if pricing is not None:
            files['shop/pricing.py'] = pricing
        return self.evaluate(files, hidden or DJANGO_HIDDEN_TESTS, time_required=time_required)

    def test_a_correct_solution_scores_100(self):
        self.assertEqual(self.evaluate_django(), {'percentage': 100, 'status': 'done'})

    def test_a_partly_correct_solution_scores_50(self):
        result = self.evaluate_django('def add(a, b):\n    return abs(a) + b\n')

        self.assertEqual(result, {'percentage': 50, 'status': 'done'})

    def test_patching_pytest_from_the_app_does_not_fake_a_pass(self):
        result = self.evaluate_django(PYTEST_CHEAT + 'def add(a, b):\n    return 999\n')

        self.assertEqual(result, {'percentage': 0, 'status': 'done'})

    def test_the_users_own_tests_and_conftest_do_not_count(self):
        result = self.evaluate_django(
            'def add(a, b):\n    return 999\n',
            **{'conftest.py': PYTEST_CHEAT, 'test_mine.py': 'def test_b():\n    assert 1\n'},
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'done'})

    def test_the_app_has_no_internet(self):
        hidden = {'test_net.py': (
            'def test_offline(client):\n'
            '    assert client.get("/online/").json() == {"online": False}\n'
        )}

        self.assertEqual(self.evaluate_django(hidden=hidden), {'percentage': 100, 'status': 'done'})

    def test_an_app_that_cannot_start_is_reported(self):
        result = self.evaluate_django('def add(a, b:\n', time_required=5)

        self.assertEqual(result, {'percentage': 0, 'status': 'app_failed'})

    def test_a_memory_hog_app_is_reported_as_out_of_memory(self):
        result = self.evaluate_django(
            'data = bytearray(2 * 1024 * 1024 * 1024)\ndef add(a, b):\n    return a + b\n',
            time_required=10,
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'out_of_memory'})

    def test_a_slow_app_times_out_and_leaves_nothing_behind(self):
        before = self.leftovers()
        hidden = {'test_slow.py': 'import time\ndef test_a(client):\n    time.sleep(60)\n'}

        result = self.evaluate_django(hidden=hidden, time_required=5)

        self.assertEqual(result, {'percentage': 0, 'status': 'timeout'})
        self.assertEqual(self.leftovers(), before)


REACT_APP = {
    'package.json': '{"name": "shop", "private": true, "type": "module"}\n',
    'index.html': (
        '<!doctype html><html><body><div id="root"></div>'
        '<script type="module" src="/src/main.jsx"></script></body></html>\n'
    ),
    'vite.config.js': (
        'import { defineConfig } from "vite";\n'
        'import react from "@vitejs/plugin-react";\n'
        'export default defineConfig({ plugins: [react()] });\n'
    ),
    'src/main.jsx': (
        'import { createRoot } from "react-dom/client";\n'
        'import Counter from "./Counter.jsx";\n'
        'createRoot(document.getElementById("root")).render(<Counter />);\n'
    ),
}

NEXT_APP = {
    'package.json': '{"name": "shop", "private": true}\n',
    'app/layout.js': (
        'export default function RootLayout({ children }) {\n'
        '  return <html><body>{children}</body></html>;\n'
        '}\n'
    ),
    'app/page.js': (
        '"use client";\n'
        'import Counter from "./Counter.jsx";\n'
        'export default function Page() { return <Counter />; }\n'
    ),
}

COUNTER = (
    'import { useState } from "react";\n'
    'export default function Counter() {\n'
    '  const [count, setCount] = useState(0);\n'
    '  return <button onClick={() => setCount(NEXT_COUNT)}>Clicked {count} times</button>;\n'
    '}\n'
)

COUNTER_HIDDEN_TESTS = {
    'test_counter.py': (
        'from playwright.sync_api import expect\n'
        'def test_starts_at_zero(page):\n'
        '    page.goto("/")\n'
        '    expect(page.get_by_role("button")).to_have_text("Clicked 0 times")\n'
        'def test_counts_clicks(page):\n'
        '    page.goto("/")\n'
        '    page.get_by_role("button").click()\n'
        '    expect(page.get_by_role("button")).to_have_text("Clicked 1 times")\n'
    ),
}


@unittest.skipUnless(docker_tests_enabled(), DOCKER_SKIP_REASON)
class FrontendLiveDockerTests(LiveDockerTestCase):
    def evaluate_app(self, framework, app, counter_path, next_count):
        files = dict(app, **{counter_path: COUNTER.replace('NEXT_COUNT', next_count)})
        return self.evaluate(
            files, COUNTER_HIDDEN_TESTS, time_required=180, field='frontend', framework=framework
        )

    def test_a_correct_react_app_scores_100(self):
        result = self.evaluate_app('react', REACT_APP, 'src/Counter.jsx', 'count + 1')

        self.assertEqual(result, {'percentage': 100, 'status': 'done'})

    def test_a_broken_react_app_scores_50(self):
        result = self.evaluate_app('react', REACT_APP, 'src/Counter.jsx', 'count')

        self.assertEqual(result, {'percentage': 50, 'status': 'done'})

    def test_a_correct_next_app_scores_100(self):
        result = self.evaluate_app('next.js', NEXT_APP, 'app/Counter.jsx', 'count + 1')

        self.assertEqual(result, {'percentage': 100, 'status': 'done'})

    def test_a_broken_next_app_scores_50(self):
        result = self.evaluate_app('next.js', NEXT_APP, 'app/Counter.jsx', 'count')

        self.assertEqual(result, {'percentage': 50, 'status': 'done'})

    def test_an_app_that_does_not_build_is_reported(self):
        files = dict(REACT_APP, **{'src/Counter.jsx': 'export default function ('})

        result = self.evaluate(
            files, COUNTER_HIDDEN_TESTS, time_required=60, field='frontend', framework='react'
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'app_failed'})


DEVOPS_HIDDEN_TESTS = {
    'test_config.py': (
        'import pytest\n'
        'import yaml\n'
        'def test_runs_as_non_root(submission_dir):\n'
        '    lines = (submission_dir / "Dockerfile").read_text().splitlines()\n'
        '    users = [line.split()[1] for line in lines if line.upper().startswith("USER ")]\n'
        '    assert users and users[-1] not in ("root", "0")\n'
        'def test_web_port_is_published(submission_dir):\n'
        '    compose = yaml.safe_load((submission_dir / "compose.yaml").read_text())\n'
        '    assert "8080:8000" in compose["services"]["web"]["ports"]\n'
        'def test_the_submission_cannot_be_changed(submission_dir):\n'
        '    with pytest.raises(OSError):\n'
        '        (submission_dir / "Dockerfile").write_text("FROM scratch")\n'
    ),
}

DEVOPS_SUBMISSION = {
    'Dockerfile': 'FROM python:3.12-slim\nRUN useradd app\nUSER app\nCMD ["python"]\n',
    'compose.yaml': 'services:\n  web:\n    build: .\n    ports:\n      - "8080:8000"\n',
}


@unittest.skipUnless(docker_tests_enabled(), DOCKER_SKIP_REASON)
class DevOpsLiveDockerTests(LiveDockerTestCase):
    def test_a_correct_config_scores_100(self):
        result = self.evaluate(DEVOPS_SUBMISSION, DEVOPS_HIDDEN_TESTS, field='devops')

        self.assertEqual(result, {'percentage': 100, 'status': 'done'})

    def test_a_root_container_loses_marks(self):
        files = dict(DEVOPS_SUBMISSION, Dockerfile='FROM python:3.12-slim\nCMD ["python"]\n')

        result = self.evaluate(files, DEVOPS_HIDDEN_TESTS, field='devops')

        self.assertEqual(result, {'percentage': 67, 'status': 'done'})

    def test_a_submitted_conftest_is_ignored(self):
        files = dict(DEVOPS_SUBMISSION, **{
            'Dockerfile': 'FROM python:3.12-slim\n',
            'conftest.py': PYTEST_CHEAT,
        })

        result = self.evaluate(files, DEVOPS_HIDDEN_TESTS, field='devops')

        self.assertEqual(result, {'percentage': 67, 'status': 'done'})


@unittest.skipUnless(docker_tests_enabled(), DOCKER_SKIP_REASON)
class CleanupLiveDockerTests(TestCase):
    def labels(self, expires_at):
        return {'veelcode.evaluator': '1', 'veelcode.expires_at': str(expires_at)}

    def test_expired_leftovers_are_removed_and_live_ones_are_kept(self):
        import time

        import docker

        from problems.services.evaluators.cleanup import remove_expired

        client = docker.from_env()
        now = int(time.time())
        expired_network = client.networks.create(
            'veelcode-cleanup-expired', internal=True, labels=self.labels(now - 10)
        )
        live_network = client.networks.create(
            'veelcode-cleanup-live', internal=True, labels=self.labels(now + 600)
        )
        expired = client.containers.run(
            'python:3.12-slim', ['sleep', '300'], detach=True,
            network=expired_network.name, labels=self.labels(now - 10),
        )
        live = client.containers.run(
            'python:3.12-slim', ['sleep', '300'], detach=True, labels=self.labels(now + 600),
        )
        self.addCleanup(lambda: [c.remove(force=True) for c in client.containers.list(
            all=True, filters={'id': [expired.id, live.id]}
        )])
        self.addCleanup(lambda: [n.remove() for n in client.networks.list(
            names=['veelcode-cleanup-expired', 'veelcode-cleanup-live']
        )])

        remove_expired()

        remaining = {c.id for c in client.containers.list(all=True, filters={'id': [expired.id, live.id]})}
        self.assertEqual(remaining, {live.id})
        networks = {n.name for n in client.networks.list(names=['veelcode-cleanup-expired', 'veelcode-cleanup-live'])}
        self.assertEqual(networks, {'veelcode-cleanup-live'})
