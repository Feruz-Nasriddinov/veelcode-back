import os
import tempfile
from pathlib import Path
import docker
from requests.exceptions import ConnectionError as DockerTimeout

TEST_SCRIPT = """
pip install -r requirements.txt pytest pytest-django

echo "=== DJANGO TESTS ==="
python manage.py test > django_test_output.txt 2>&1
DJANGO_EXIT=$?

echo "=== PYTEST TESTS ==="
pytest --junitxml=pytest-results.xml > pytest_output.txt 2>&1
PYTEST_EXIT=$?

echo "=== DJANGO OUTPUT ==="; cat django_test_output.txt
echo "=== PYTEST OUTPUT ==="; cat pytest_output.txt
echo "=== PYTEST XML ==="; cat pytest-results.xml 2>/dev/null

echo "=== EXIT CODES ==="
echo "django_exit=$DJANGO_EXIT"
echo "pytest_exit=$PYTEST_EXIT"
"""
# Deliberately no `exit 1` here — bash always exits 0.
# Pass/fail is decided by parsing the EXIT CODES lines, not the container's own status.

def evaluate(files, timeout=120):
    client = docker.from_env()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        for filename, content in files.items():
            file_path = temp_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        (temp_path / "requirements.txt").touch(exist_ok=True)  # don't crash if missing

        container = client.containers.run(
            "django-evaluator",
            ["bash", "-c", TEST_SCRIPT],
            volumes={temp_dir: {"bind": "/app", "mode": "rw"}},
            working_dir="/app",
            user=f"{os.getuid()}:{os.getgid()}",   # avoid root-owned files / cleanup failures
            mem_limit="512m",
            pids_limit=128,
            detach=True,   # take manual control instead of run()'s exception-on-failure behavior
        )

        try:
            container.wait(timeout=timeout)
            output = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        except DockerTimeout:
            output = "TIMED OUT after %ds" % timeout
        finally:
            container.remove(force=True)

        return output