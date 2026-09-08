import tempfile
from pathlib import Path
import docker


def evaluate(files):
    client = docker.from_env()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        for filename, content in files.items():
            file_path = temp_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        container = client.containers.run(
            "django-evaluator",
            """
            bash -c '
                pip install -r requirements.txt pytest pytest-django

                echo "=== DJANGO TESTS ==="
                python manage.py test > django_test_output.txt 2>&1
                DJANGO_EXIT=$?

                echo "=== PYTEST TESTS ==="
                pytest --junitxml=pytest-results.xml > pytest_output.txt 2>&1
                PYTEST_EXIT=$?

                echo "=== DJANGO OUTPUT ==="
                cat django_test_output.txt

                echo "=== PYTEST OUTPUT ==="
                cat pytest_output.txt

                echo "=== PYTEST XML ==="
                cat pytest-results.xml

                echo "=== EXIT CODES ==="
                echo "django_exit=$DJANGO_EXIT"
                echo "pytest_exit=$PYTEST_EXIT"

                if [ $DJANGO_EXIT -ne 0 ] || [ $PYTEST_EXIT -ne 0 ]; then
                    exit 1
                fi
            '
            """,
            volumes={
                temp_dir: {
                    "bind": "/app",
                    "mode": "rw",
                }
            },
            working_dir="/app",
            remove=True,
        )

        return container.decode()