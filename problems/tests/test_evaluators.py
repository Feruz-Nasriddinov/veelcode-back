import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase

from problems.models import ProblemFile

from .base import ProblemsTestCase


class EvaluatorTestCase(ProblemsTestCase):
    def run_evaluation(
        self, files=None, problem=None, report=None, grader_state=None, runner_state=None,
        wait_exc=None, reload_exc=None, run_exc=None,
    ):
        import docker as real_docker

        from problems.services.evaluators import evaluate

        problem = problem or self.make_problem_with_hidden_tests()
        grader = MagicMock(name='grader')
        grader.attrs = {'State': grader_state or {'Running': False, 'ExitCode': 0}}
        if wait_exc is not None:
            grader.wait.side_effect = wait_exc
        if reload_exc is not None:
            grader.reload.side_effect = reload_exc
        runner = MagicMock(name='runner')
        runner.attrs = {'State': runner_state or {'Running': True}}
        self.grader, self.runner, self.calls = grader, runner, {}

        def fake_run(image, command, **kwargs):
            role = 'runner' if 'name' in kwargs else 'grader'
            if role == 'grader' and run_exc is not None:
                raise run_exc
            mounts = {}
            for host, spec in kwargs['volumes'].items():
                root = Path(host)
                mounts[spec['bind']] = {
                    p.relative_to(root).as_posix(): p.read_text()
                    for p in root.rglob('*') if p.is_file()
                }
                if role == 'grader' and spec['bind'] == '/grader' and report is not None:
                    (root / 'pytest-results.xml').write_text(report)
            self.calls[role] = {'image': image, 'command': command, 'kwargs': kwargs, 'mounts': mounts}
            return runner if role == 'runner' else grader

        with patch('problems.services.evaluators.base.docker') as docker_mod:
            docker_mod.errors = real_docker.errors
            self.client = docker_mod.from_env.return_value
            self.client.containers.run.side_effect = fake_run
            self.network = self.client.networks.create.return_value
            self.network.name = 'veelcode-net'
            return evaluate(files or {'main.py': 'x = 1'}, problem.id)


class EvaluatorDispatchTests(ProblemsTestCase):
    def test_each_supported_problem_type_gets_its_evaluator(self):
        from problems.services.evaluators import (
            DevOpsEvaluator, DjangoEvaluator, NextEvaluator, ReactEvaluator, get_evaluator,
        )

        cases = [
            ('backend', 'django', DjangoEvaluator),
            ('backend', 'django rest framework', DjangoEvaluator),
            ('frontend', 'react', ReactEvaluator),
            ('frontend', 'next.js', NextEvaluator),
            ('devops', 'django', DevOpsEvaluator),
        ]
        for field, framework, expected in cases:
            with self.subTest(field=field, framework=framework):
                problem = self.make_problem(field=field, framework=framework)
                self.assertIsInstance(get_evaluator(problem), expected)

    @patch('problems.services.evaluators.base.docker')
    def test_an_unsupported_problem_type_never_starts_a_container(self, docker_mod):
        from problems.services.evaluators import evaluate

        problem = self.make_problem_with_hidden_tests(field='backend', framework='spring boot')

        result = evaluate({'main.py': 'x = 1'}, problem.id)

        self.assertEqual(result, {'percentage': 0, 'status': 'unsupported'})
        docker_mod.from_env.assert_not_called()


class BackendEvaluatorTests(EvaluatorTestCase):
    def test_the_app_and_the_grader_run_in_separate_containers(self):
        self.run_evaluation()

        self.assertEqual(self.calls['runner']['image'], 'django-evaluator')
        self.assertEqual(self.calls['grader']['image'], 'veelcode-backend-grader')

    def test_both_containers_share_a_private_network_without_internet(self):
        self.run_evaluation()

        self.assertTrue(self.client.networks.create.call_args.kwargs['internal'])
        for role in ('runner', 'grader'):
            with self.subTest(role=role):
                self.assertEqual(self.calls[role]['kwargs']['network'], 'veelcode-net')
                self.assertNotIn('network_mode', self.calls[role]['kwargs'])

    def test_the_grader_is_pointed_at_the_app(self):
        self.run_evaluation()

        app_name = self.calls['runner']['kwargs']['name']
        env = self.calls['grader']['kwargs']['environment']
        self.assertEqual(env['APP_URL'], f'http://{app_name}:8000')

    def test_submitted_files_never_reach_the_grader(self):
        self.run_evaluation({'app.py': 'x = 1', 'conftest.py': 'evil'})

        self.assertEqual(self.calls['runner']['mounts']['/src'], {'app.py': 'x = 1', 'conftest.py': 'evil'})
        self.assertEqual(list(self.calls['grader']['mounts']), ['/grader'])
        self.assertEqual(list(self.calls['grader']['mounts']['/grader']), ['test_hidden.py'])

    def test_hidden_tests_never_reach_the_app(self):
        self.run_evaluation({'app.py': 'x = 1'})

        self.assertNotIn('test_hidden.py', self.calls['runner']['mounts']['/src'])

    def test_only_hidden_test_modules_are_passed_to_pytest(self):
        problem = self.make_problem_with_hidden_tests({
            'tests/conftest.py': 'x', 'tests/test_hidden.py': 'x', 'tests/data.json': '{}',
        })
        ProblemFile.objects.create(problem=problem, directory='test_visible.py', content='x')

        self.run_evaluation(problem=problem)

        command = self.calls['grader']['command']
        self.assertEqual(command[command.index('--') + 1:], ['tests/test_hidden.py'])

    def test_every_container_has_memory_and_pid_limits(self):
        self.run_evaluation()

        for role in ('runner', 'grader'):
            with self.subTest(role=role):
                kwargs = self.calls[role]['kwargs']
                self.assertTrue(kwargs['mem_limit'])
                self.assertTrue(kwargs['pids_limit'])

    def test_every_container_is_locked_down(self):
        self.run_evaluation()

        for role in ('runner', 'grader'):
            with self.subTest(role=role):
                kwargs = self.calls[role]['kwargs']
                self.assertEqual(kwargs['cap_drop'], ['ALL'])
                self.assertIn('no-new-privileges', kwargs['security_opt'])
                self.assertEqual(kwargs['memswap_limit'], kwargs['mem_limit'])
                self.assertTrue(kwargs['nano_cpus'])
                self.assertIn('size=', kwargs['tmpfs']['/tmp'])

    def test_the_submission_is_mounted_read_only_and_copied_into_a_size_capped_workspace(self):
        self.run_evaluation()

        runner = self.calls['runner']['kwargs']
        self.assertEqual([v['mode'] for v in runner['volumes'].values()], ['ro'])
        self.assertIn('size=128m', runner['tmpfs']['/app'])
        self.assertTrue(runner['read_only'])

    def test_containers_never_run_as_root(self):
        with patch('problems.services.evaluators.base.os.getuid', return_value=0), \
                patch('problems.services.evaluators.base.hand_over'):
            self.run_evaluation()

        for role in ('runner', 'grader'):
            with self.subTest(role=role):
                self.assertEqual(self.calls[role]['kwargs']['user'], '65534:65534')

    def test_containers_and_network_are_removed(self):
        self.run_evaluation(report='<testsuite tests="1"/>')

        self.grader.remove.assert_called_once_with(force=True)
        self.runner.remove.assert_called_once_with(force=True)
        self.network.remove.assert_called_once()

    def test_the_app_is_removed_when_the_grader_fails_to_start(self):
        import docker as real_docker

        from problems.services.evaluators import ContainerInfraError

        with self.assertRaises(ContainerInfraError):
            self.run_evaluation(run_exc=real_docker.errors.ImageNotFound('no image'))

        self.runner.remove.assert_called_once_with(force=True)
        self.network.remove.assert_called_once()

    def test_the_report_is_scored(self):
        result = self.run_evaluation(report='<testsuite tests="4" failures="1"/>')

        self.assertEqual(result, {'percentage': 75, 'status': 'done'})

    def test_a_missing_report_is_an_internal_failure(self):
        self.assertEqual(self.run_evaluation(), {'percentage': 0, 'status': 'failed'})

    def test_an_app_that_never_starts_is_reported(self):
        result = self.run_evaluation(grader_state={'Running': False, 'ExitCode': 90})

        self.assertEqual(result, {'percentage': 0, 'status': 'app_failed'})

    def test_an_oom_killed_app_is_reported_as_out_of_memory(self):
        result = self.run_evaluation(
            report='<testsuite tests="1"/>', runner_state={'Running': False, 'OOMKilled': True}
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'out_of_memory'})

    def test_an_oom_killed_grader_is_reported_as_out_of_memory(self):
        result = self.run_evaluation(grader_state={'Running': False, 'OOMKilled': True})

        self.assertEqual(result, {'percentage': 0, 'status': 'out_of_memory'})

    def test_a_grader_still_running_at_the_deadline_is_a_timeout(self):
        from itertools import chain, repeat

        from requests.exceptions import ReadTimeout

        with patch('problems.services.evaluators.base.time.monotonic', side_effect=chain([0], repeat(1000))):
            result = self.run_evaluation(
                wait_exc=ReadTimeout('timed out'), grader_state={'Running': True}
            )

        self.assertEqual(result, {'percentage': 0, 'status': 'timeout'})
        self.grader.kill.assert_called_once()
        self.runner.remove.assert_called_once_with(force=True)

    def test_an_app_that_exits_stops_the_grader_early(self):
        from requests.exceptions import ReadTimeout

        result = self.run_evaluation(
            wait_exc=ReadTimeout('timed out'),
            grader_state={'Running': True},
            runner_state={'Running': False, 'ExitCode': 2},
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'app_failed'})
        self.grader.kill.assert_called_once()
        self.assertEqual(self.grader.wait.call_count, 1)

    def test_a_grader_that_finished_during_the_timeout_is_still_scored(self):
        from requests.exceptions import ConnectionError

        result = self.run_evaluation(
            wait_exc=ConnectionError('Read timed out.'),
            grader_state={'Running': False, 'ExitCode': 1},
            report='<testsuite tests="2" failures="1"/>',
        )

        self.assertEqual(result, {'percentage': 50, 'status': 'done'})
        self.grader.kill.assert_not_called()

    def test_losing_the_docker_daemon_is_an_infra_error(self):
        import docker as real_docker
        from requests.exceptions import ConnectionError

        from problems.services.evaluators import ContainerInfraError

        with self.assertRaises(ContainerInfraError):
            self.run_evaluation(
                wait_exc=ConnectionError('daemon gone'),
                reload_exc=real_docker.errors.APIError('daemon gone'),
            )

    def test_escaping_path_never_reaches_docker(self):
        with self.assertRaises(ValueError):
            self.run_evaluation({'../escape.py': 'x = 1'})

        self.client.containers.run.assert_not_called()

    def test_absolute_path_never_reaches_docker(self):
        with self.assertRaises(ValueError):
            self.run_evaluation({'/etc/passwd': 'root'})

        self.client.containers.run.assert_not_called()

    @patch('problems.services.evaluators.base.docker')
    def test_a_problem_without_hidden_tests_never_starts_a_container(self, docker_mod):
        from problems.services.evaluators import evaluate

        problem = self.make_problem_with_hidden_tests({'conftest.py': 'x', 'data.json': '{}'})

        result = evaluate({'app.py': 'x = 1'}, problem.id)

        self.assertEqual(result, {'percentage': 0, 'status': 'no_tests'})
        docker_mod.from_env.return_value.containers.run.assert_not_called()


class FrontendEvaluatorTests(EvaluatorTestCase):
    def make_frontend_problem(self, framework):
        return self.make_problem_with_hidden_tests(field='frontend', framework=framework)

    def test_the_browser_grader_is_pointed_at_the_app(self):
        self.run_evaluation(problem=self.make_frontend_problem('react'))

        command = self.calls['grader']['command']
        app_url = self.calls['grader']['kwargs']['environment']['APP_URL']
        self.assertEqual(command[command.index('--base-url') + 1], app_url)
        self.assertEqual(self.calls['grader']['image'], 'veelcode-frontend-grader')

    def test_the_submission_is_mounted_read_only(self):
        self.run_evaluation(problem=self.make_frontend_problem('next.js'))

        self.assertEqual(self.calls['runner']['kwargs']['volumes'].popitem()[1]['mode'], 'ro')
        self.assertEqual(self.calls['runner']['image'], 'veelcode-frontend-runner')

    def test_react_and_next_build_differently(self):
        self.run_evaluation(problem=self.make_frontend_problem('react'))
        react_command = ' '.join(self.calls['runner']['command'])
        self.run_evaluation(problem=self.make_frontend_problem('next.js'))
        next_command = ' '.join(self.calls['runner']['command'])

        self.assertIn('vite build', react_command)
        self.assertIn('next build', next_command)


class DevOpsEvaluatorTests(EvaluatorTestCase):
    def setUp(self):
        super().setUp()
        self.problem = self.make_problem_with_hidden_tests(field='devops')

    def test_no_user_code_is_run(self):
        self.run_evaluation({'Dockerfile': 'FROM python'}, problem=self.problem)

        self.assertNotIn('runner', self.calls)
        self.client.networks.create.assert_not_called()

    def test_the_grader_has_no_network(self):
        self.run_evaluation(problem=self.problem)

        self.assertEqual(self.calls['grader']['kwargs']['network_mode'], 'none')

    def test_the_submission_is_mounted_read_only_next_to_the_hidden_tests(self):
        self.run_evaluation({'Dockerfile': 'FROM python'}, problem=self.problem)

        volumes = {spec['bind']: spec['mode'] for spec in self.calls['grader']['kwargs']['volumes'].values()}
        self.assertEqual(volumes, {'/grader': 'rw', '/submission': 'ro'})
        self.assertEqual(self.calls['grader']['mounts']['/submission'], {'Dockerfile': 'FROM python'})
        self.assertEqual(self.calls['grader']['kwargs']['environment']['SUBMISSION_DIR'], '/submission')


class EvaluatorLabelTests(EvaluatorTestCase):
    def test_every_container_and_network_is_labelled_with_a_deadline(self):
        import time

        before = time.time()
        self.run_evaluation(problem=self.make_problem_with_hidden_tests(time_required=30))

        labels = [self.calls[role]['kwargs']['labels'] for role in ('runner', 'grader')]
        labels.append(self.client.networks.create.call_args.kwargs['labels'])
        for label in labels:
            self.assertEqual(label['veelcode.evaluator'], '1')
            self.assertGreaterEqual(int(label['veelcode.expires_at']), int(before) + 30 + 5 + 120)


class EvaluatorCleanupTests(TestCase):
    NOW = 1_000_000

    def resource(self, expires_at=None, labels=None):
        resource = MagicMock()
        resource.labels = labels if labels is not None else {
            'veelcode.evaluator': '1', 'veelcode.expires_at': str(expires_at),
        }
        resource.attrs = {'Labels': resource.labels}
        return resource

    def cleanup(self, containers=(), networks=()):
        import docker as real_docker

        from problems.services.evaluators.cleanup import remove_expired

        with patch('problems.services.evaluators.cleanup.docker') as docker_mod:
            docker_mod.errors = real_docker.errors
            client = docker_mod.from_env.return_value
            client.containers.list.return_value = list(containers)
            client.networks.list.return_value = list(networks)
            return remove_expired(now=self.NOW), client

    def test_expired_containers_and_networks_are_removed(self):
        container, network = self.resource(self.NOW - 1), self.resource(self.NOW - 1)

        removed, _ = self.cleanup([container], [network])

        container.remove.assert_called_once_with(force=True)
        network.remove.assert_called_once()
        self.assertEqual(removed, {'containers': 1, 'networks': 1})

    def test_running_evaluations_are_left_alone(self):
        container, network = self.resource(self.NOW + 60), self.resource(self.NOW + 60)

        removed, _ = self.cleanup([container], [network])

        container.remove.assert_not_called()
        network.remove.assert_not_called()
        self.assertEqual(removed, {'containers': 0, 'networks': 0})

    def test_only_labelled_resources_are_listed(self):
        _, client = self.cleanup()

        self.assertEqual(
            client.containers.list.call_args.kwargs,
            {'all': True, 'filters': {'label': 'veelcode.evaluator=1'}},
        )
        self.assertEqual(
            client.networks.list.call_args.kwargs, {'filters': {'label': 'veelcode.evaluator=1'}}
        )

    def test_a_missing_or_broken_deadline_is_left_alone(self):
        missing = self.resource(labels={'veelcode.evaluator': '1'})
        broken = self.resource(labels={'veelcode.evaluator': '1', 'veelcode.expires_at': 'soon'})

        self.cleanup([missing, broken])

        missing.remove.assert_not_called()
        broken.remove.assert_not_called()

    def test_one_failure_does_not_stop_the_rest(self):
        import docker as real_docker

        stuck, other = self.resource(self.NOW - 1), self.resource(self.NOW - 1)
        stuck.remove.side_effect = real_docker.errors.APIError('busy')
        network = self.resource(self.NOW - 1)

        removed, _ = self.cleanup([stuck, other], [network])

        other.remove.assert_called_once_with(force=True)
        network.remove.assert_called_once()
        self.assertEqual(removed, {'containers': 1, 'networks': 1})

    def test_docker_being_down_is_not_an_error(self):
        import docker as real_docker

        from problems.services.evaluators.cleanup import remove_expired

        with patch('problems.services.evaluators.cleanup.docker') as docker_mod:
            docker_mod.errors = real_docker.errors
            docker_mod.from_env.side_effect = real_docker.errors.DockerException('down')

            self.assertEqual(remove_expired(), {'containers': 0, 'networks': 0})

    def test_the_cleanup_task_is_scheduled(self):
        from django.conf import settings

        from problems.tasks import cleanup_evaluator_leftovers

        tasks = [entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()]
        self.assertIn(cleanup_evaluator_leftovers.name, tasks)


class EvaluatorScoringTests(TestCase):
    def score(self, xml):
        from problems.services.evaluators import score_report

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        report = Path(temp_dir.name) / 'pytest-results.xml'
        report.write_text(xml)
        return score_report(report)

    def suite(self, **attrs):
        rendered = ' '.join(f'{name}="{value}"' for name, value in attrs.items())
        return f'<testsuites><testsuite {rendered}/></testsuites>'

    def test_all_passing_is_100(self):
        self.assertEqual(self.score(self.suite(tests=4, failures=0, errors=0, skipped=0)), 100)

    def test_three_of_four_rounds_to_75(self):
        self.assertEqual(self.score(self.suite(tests=4, failures=1, errors=0, skipped=0)), 75)

    def test_two_of_three_rounds_to_67(self):
        self.assertEqual(self.score(self.suite(tests=3, failures=1, errors=0, skipped=0)), 67)

    def test_errors_count_against_the_score(self):
        self.assertEqual(self.score(self.suite(tests=2, failures=0, errors=1, skipped=0)), 50)

    def test_a_skipped_test_is_not_a_passing_test(self):
        self.assertEqual(self.score(self.suite(tests=4, failures=0, errors=0, skipped=3)), 25)

    def test_skipping_everything_scores_zero(self):
        self.assertEqual(self.score(self.suite(tests=4, failures=0, errors=0, skipped=4)), 0)

    def test_no_tests_scores_zero(self):
        self.assertEqual(self.score(self.suite(tests=0)), 0)

    def test_a_bare_testsuite_root_is_read(self):
        self.assertEqual(self.score('<testsuite tests="2" failures="1"/>'), 50)

    def test_malformed_xml_scores_zero(self):
        self.assertEqual(self.score('<testsuites>'), 0)

    def test_a_report_without_a_testsuite_scores_zero(self):
        self.assertEqual(self.score('<testsuites></testsuites>'), 0)

    def test_non_numeric_attributes_score_zero(self):
        self.assertEqual(self.score('<testsuite tests="lots" failures="many"/>'), 0)

    def test_counts_larger_than_the_total_never_go_negative(self):
        self.assertEqual(self.score('<testsuite tests="2" failures="3" skipped="4"/>'), 0)
