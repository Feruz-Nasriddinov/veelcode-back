import os
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
import docker
from requests.exceptions import ReadTimeout
from problems.models import Problem
from rest_framework.generics import get_object_or_404
RUN_SCRIPT = """
pip install -r requirements.txt pytest pytest-django > /tmp/pip.log 2>&1
pytest --junitxml=pytest-results.xml > /tmp/pytest.log 2>&1
"""

def evaluate(files, problem_id):
    problem = get_object_or_404(Problem, id = problem_id)
    
    timeout = problem.time_required + 10#prototype for the test/early version 
    client = docker.from_env()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir).resolve()

        for filename, content in files.items():

            file_path = (temp_path / filename).resolve()

            if not file_path.is_relative_to(temp_path):
                raise ValueError("Submitted file path escapes the working directory.")
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        (temp_path / "requirements.txt").touch(exist_ok=True)

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

        try:
            container.wait(timeout=timeout)
        except ReadTimeout:
            container.kill()
            return {'percentage': 0, 'status': 'timeout'}
        finally:
            container.remove(force=True)

        results_file = temp_path / "pytest-results.xml"
        if not results_file.exists():
            return {"percentage": 0, 'status': 'failed'}

        root = ET.parse(results_file).getroot()
        suite = root.find("testsuite") if root.tag == "testsuites" else root

        total = int(suite.attrib.get("tests", 0))
        failed = int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
        percentage = round((total - failed) / total * 100) if total else 0

        return {"percentage": percentage, "status": 'done'}