import logging
import os
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

import docker
from requests.exceptions import ConnectionError as RequestsConnectionError, ReadTimeout

logger = logging.getLogger(__name__)

CONTAINER_TIMEOUT_GRACE = 5
RUNNER_POLL_SECONDS = 1
APP_PORT = 8000
APP_NOT_READY_EXIT_CODE = 90
RESULTS_FILE = 'pytest-results.xml'
CLEANUP_GRACE = 120
EVALUATOR_LABEL = 'veelcode.evaluator'
EXPIRES_LABEL = 'veelcode.expires_at'

class ContainerInfraError(Exception):
    pass

class Evaluator:
    runner_image = None
    runner_mount_mode = 'ro'
    runner_mem_limit = '512m'
    runner_pids_limit = 128

    grader_image = None
    grader_mem_limit = '512m'
    grader_pids_limit = 128

    def __init__(self, problem):
        self.problem = problem
        self.timeout = problem.time_required + CONTAINER_TIMEOUT_GRACE

    def runner_command(self):
        raise NotImplementedError

    def grader_args(self, app_url):
        return []

    def evaluate(self, files):
        hidden_files = dict(
            self.problem.files.filter(is_hidden=True).values_list('directory', 'content')
        )
        test_paths = [
            path for path in hidden_files
            if path.endswith('.py') and PurePosixPath(path).name != 'conftest.py'
        ]
        if not test_paths:
            return {'percentage': 0, 'status': 'no_tests'}

        with tempfile.TemporaryDirectory() as submission_dir, tempfile.TemporaryDirectory() as grader_dir:
            submission_path = Path(submission_dir).resolve()
            grader_path = Path(grader_dir).resolve()
            write_files(submission_path, files)
            write_files(grader_path, hidden_files)

            try:
                client = docker.from_env()
            except docker.errors.DockerException as e:
                raise ContainerInfraError(f"Docker unavailable: {e}")

            run = _Run(self, client, submission_path, grader_path, test_paths)
            try:
                return run.execute()
            finally:
                run.cleanup()


class _Run:
    def __init__(self, evaluator, client, submission_path, grader_path, test_paths):
        self.evaluator = evaluator
        self.client = client
        self.submission_path = submission_path
        self.grader_path = grader_path
        self.test_paths = test_paths
        self.run_id = uuid.uuid4().hex[:12]
        self.labels = {
            EVALUATOR_LABEL: '1',
            EXPIRES_LABEL: str(int(time.time()) + evaluator.timeout + CLEANUP_GRACE),
        }
        self.network = None
        self.runner = None
        self.grader = None
        self.runner_exited = False

    def execute(self):
        evaluator = self.evaluator
        environment = {'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'}
        volumes = {str(self.grader_path): {'bind': '/grader', 'mode': 'rw'}}
        network_options = {'network_mode': 'none'}
        app_url = None

        if evaluator.runner_image:
            self.network = self._call(
                self.client.networks.create, f'veelcode-{self.run_id}', driver='bridge', internal=True,
                labels=self.labels,
            )
            network_options = {'network': self.network.name}
            app_name = f'veelcode-app-{self.run_id}'
            app_url = f'http://{app_name}:{APP_PORT}'
            self.runner = self._start(
                evaluator.runner_image,
                evaluator.runner_command(),
                name=app_name,
                volumes={str(self.submission_path): {'bind': '/app', 'mode': evaluator.runner_mount_mode}},
                working_dir='/app',
                environment={'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1'},
                mem_limit=evaluator.runner_mem_limit,
                pids_limit=evaluator.runner_pids_limit,
                **network_options,
            )
            environment['APP_URL'] = app_url
            environment['APP_READY_TIMEOUT'] = str(evaluator.problem.time_required)
        else:
            volumes[str(self.submission_path)] = {'bind': '/submission', 'mode': 'ro'}
            environment['SUBMISSION_DIR'] = '/submission'

        command = [
            'pytest', '-p', 'veelcode_grader', '-p', 'no:cacheprovider',
            f'--junitxml=/grader/{RESULTS_FILE}',
            *evaluator.grader_args(app_url),
            '--', *self.test_paths,
        ]
        self.grader = self._start(
            evaluator.grader_image,
            command,
            volumes=volumes,
            working_dir='/grader',
            environment=environment,
            mem_limit=evaluator.grader_mem_limit,
            pids_limit=evaluator.grader_pids_limit,
            **network_options,
        )

        state = self._wait(self.grader)
        if state is None and not self.runner_exited:
            return {'percentage': 0, 'status': 'timeout'}

        state = state or {}
        runner_state = (_container_state(self.runner) or {}) if self.runner else {}
        if state.get('OOMKilled') or runner_state.get('OOMKilled'):
            return {'percentage': 0, 'status': 'out_of_memory'}
        if self.runner_exited or state.get('ExitCode') == APP_NOT_READY_EXIT_CODE:
            return {'percentage': 0, 'status': 'app_failed'}

        results_file = self.grader_path / RESULTS_FILE
        if not results_file.exists():
            return {'percentage': 0, 'status': 'failed'}

        return {'percentage': score_report(results_file), 'status': 'done'}

    def _call(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except docker.errors.DockerException as e:
            raise ContainerInfraError(f"Docker call failed: {e}")

    def _start(self, image, command, **kwargs):
        return self._call(
            self.client.containers.run,
            image,
            command,
            user=f'{os.getuid()}:{os.getgid()}',
            labels=self.labels,
            detach=True,
            **kwargs,
        )

    def _wait(self, container):
        deadline = time.monotonic() + self.evaluator.timeout
        while True:
            poll = RUNNER_POLL_SECONDS if self.runner else self.evaluator.timeout
            try:
                container.wait(timeout=max(1, min(poll, deadline - time.monotonic())))
                return _container_state(container) or {}
            except (ReadTimeout, RequestsConnectionError) as e:
                state = _container_state(container)
                if state is None:
                    raise ContainerInfraError(f"Lost the Docker connection while waiting: {e}")
                if not state.get('Running'):
                    return state
                if self._runner_stopped():
                    self.runner_exited = True
                elif time.monotonic() < deadline:
                    continue
                try:
                    container.kill()
                except docker.errors.APIError:
                    logger.warning(f"Failed to kill grader for problem {self.evaluator.problem.id}")
                return None
            except docker.errors.APIError as e:
                raise ContainerInfraError(f"Error while waiting on container: {e}")

    def _runner_stopped(self):
        if self.runner is None:
            return False
        state = _container_state(self.runner)
        return state is not None and not state.get('Running')

    def cleanup(self):
        for container in (self.grader, self.runner):
            if container is None:
                continue
            try:
                container.remove(force=True)
            except docker.errors.APIError:
                logger.warning(f"Failed to remove container for problem {self.evaluator.problem.id}")
        if self.network is not None:
            try:
                self.network.remove()
            except docker.errors.APIError:
                logger.warning(f"Failed to remove network for problem {self.evaluator.problem.id}")


def _container_state(container):
    try:
        container.reload()
    except (docker.errors.APIError, RequestsConnectionError, ReadTimeout):
        return None
    return container.attrs.get('State') or {}

def write_files(root, files):
    for filename, content in files.items():
        file_path = (root / filename).resolve()
        if not file_path.is_relative_to(root):
            raise ValueError("Submitted file path escapes the working directory.")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

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
