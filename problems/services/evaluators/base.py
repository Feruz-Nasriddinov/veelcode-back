import os
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
import docker
from requests.exceptions import ConnectionError as RequestsConnectionError, ReadTimeout
from problems.models import Problem
from rest_framework.generics import get_object_or_404
import logging

logger = logging.getLogger(__name__)

CONTAINER_TIMEOUT_GRACE = 5

RUN_SCRIPT = """
pytest --junitxml=pytest-results.xml > /tmp/pytest.log 2>&1
"""

class ContainerInfraError(Exception):
    pass

def _container_state(container):
    try:
        container.reload()
    except (docker.errors.APIError, RequestsConnectionError, ReadTimeout):
        return None
    return container.attrs.get('State') or {}

def evaluate(files, problem_id):
    problem = get_object_or_404(Problem, id=problem_id)
    timeout = problem.time_required + CONTAINER_TIMEOUT_GRACE

    try:
        client = docker.from_env()
    except docker.errors.DockerException as e:
        raise ContainerInfraError(f"Docker unavailable: {e}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir).resolve()

        for filename, content in files.items():
            file_path = (temp_path / filename).resolve()
            if not file_path.is_relative_to(temp_path):
                raise ValueError("Submitted file path escapes the working directory.")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        try:
            container = client.containers.run(
                "django-evaluator",
                ["bash", "-c", RUN_SCRIPT],
                volumes={str(temp_path): {"bind": "/app", "mode": "rw"}},
                working_dir="/app",
                user=f'{os.getuid()}:{os.getgid()}',
                environment={'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'},
                mem_limit="512m",
                pids_limit=128,
                network_mode="none",
                detach=True,
            )
        except (docker.errors.APIError, docker.errors.ImageNotFound) as e:
            raise ContainerInfraError(f"Container failed to start: {e}")

        state = {}
        try:
            container.wait(timeout=timeout)
            state = _container_state(container) or {}
        except (ReadTimeout, RequestsConnectionError) as e:
            state = _container_state(container)
            if state is None:
                raise ContainerInfraError(f"Lost the Docker connection while waiting: {e}")
            if state.get('Running'):
                try:
                    container.kill()
                except docker.errors.APIError:
                    logger.warning(f"Failed to kill container for problem {problem_id}")
                return {'percentage': 0, 'status': 'timeout'}
        except docker.errors.APIError as e:
            raise ContainerInfraError(f"Error while waiting on container: {e}")
        finally:
            try:
                container.remove(force=True)
            except docker.errors.APIError:
                logger.warning(f"Failed to remove container for problem {problem_id}")

        if state.get('OOMKilled'):
            return {'percentage': 0, 'status': 'out_of_memory'}

        results_file = temp_path / "pytest-results.xml"
        if not results_file.exists():
            return {"percentage": 0, 'status': 'failed'}

        return {"percentage": score_report(results_file), "status": 'done'}

def score_report(results_file):
    try:
        root = ET.parse(results_file).getroot()
    except ET.ParseError:
        return 0

    suite = root.find("testsuite") if root.tag == "testsuites" else root
    if suite is None:
        return 0

    def count(name):
        try:
            return int(suite.attrib.get(name, 0))
        except (TypeError, ValueError):
            return 0

    total = count("tests")
    if total <= 0:
        return 0

    not_passed = count("failures") + count("errors") + count("skipped")
    passed = max(0, total - not_passed)

    return round(passed / total * 100)
