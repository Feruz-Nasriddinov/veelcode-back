import os
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
import docker
from requests.exceptions import ReadTimeout
from models import Problem
from rest_framework.generics import get_object_or_404
RUN_SCRIPT = """
pip install -r requirements.txt pytest pytest-django > /tmp/pip.log 2>&1
pytest --junitxml=pytest-results.xml > /tmp/pytest.log 2>&1
"""

def evaluate(files, problem_id):
    problem = get_object_or_404(Problem, id = problem_id)
    
    timeout = problem.time_required
    client = docker.from_env()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        for filename, content in files.items():
            file_path = temp_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        (temp_path / "requirements.txt").touch(exist_ok=True)

        container = client.containers.run(
            "django-evaluator",
            ["bash", "-c", RUN_SCRIPT],
            volumes={temp_dir: {"bind": "/app", "mode": "rw"}},
            working_dir="/app",
            mem_limit="512m",
            pids_limit=128,
            detach=True,  
        )

        try:
            container.wait(timeout=timeout)
        except ReadTimeout:
            container.kill()
        finally:
            container.remove(force=True)

        results_file = temp_path / "pytest-results.xml"
        if not results_file.exists():
            return {"total": 0, "failed": 0, "percentage": 0.0}

        root = ET.parse(results_file).getroot()
        suite = root.find("testsuite") if root.tag == "testsuites" else root

        total = int(suite.attrib.get("tests", 0))
        failed = int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
        percentage = round((total - failed) / total * 100, 2) if total else 0.0

        return {"percentage": percentage}