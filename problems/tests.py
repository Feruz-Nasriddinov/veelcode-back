import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from problems.models import Problem, ProblemFile
from users.models import User, UserDetail

PASSWORD = 'Sup3rSecret!pass'


class ProblemsTestCase(TestCase):
    client_class = APIClient

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(
            username='ryota', email='ryota@example.com', password=PASSWORD
        )
        self.client.force_authenticate(self.user)

    def make_problem(self, **overrides):
        data = {
            'title': 'Fix the cache',
            'description': 'A broken cache layer',
            'difficulty': 'medium',
            'status': 'accepted',
            'field': 'backend',
            'language': 'python',
            'framework': 'django',
            'created_by': self.user,
        }
        data.update(overrides)
        return Problem.objects.create(**data)


class ProblemModelTests(ProblemsTestCase):
    def test_str(self):
        problem = self.make_problem()

        self.assertEqual(str(problem), 'Fix the cache-medium')

    def test_id_is_a_uuid_by_default(self):
        problem = self.make_problem()

        self.assertIsInstance(problem.id, uuid.UUID)

    def test_time_required_defaults_to_0(self):
        problem = self.make_problem()

        self.assertEqual(problem.time_required, 0)

    def test_creator_is_protected_from_deletion(self):
        from django.db.models import ProtectedError

        self.make_problem()

        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_description_has_a_max_length(self):
        field = Problem._meta.get_field('description')

        self.assertEqual(field.max_length, 500)

    def test_field_language_and_framework_are_stored(self):
        problem = self.make_problem(
            field='frontend', language='typescript', framework='react'
        )
        problem.refresh_from_db()

        self.assertEqual(problem.field, 'frontend')
        self.assertEqual(problem.language, 'typescript')
        self.assertEqual(problem.framework, 'react')

    def test_a_value_outside_the_choices_is_rejected(self):
        from django.core.exceptions import ValidationError

        problem = self.make_problem(field='mobile')

        with self.assertRaises(ValidationError):
            problem.full_clean()

    def test_problem_file_str_and_cascade(self):
        problem = self.make_problem()
        pf = ProblemFile.objects.create(problem=problem, directory='app/views.py', content='x = 1')

        self.assertEqual(str(pf), 'Fix the cache-app/views.py')

        problem.delete()
        self.assertEqual(ProblemFile.objects.count(), 0)


class ProblemListViewTests(ProblemsTestCase):
    url = '/api/problems/'

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_returns_accepted_problems(self):
        self.make_problem(title='Accepted one')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], 'Accepted one')

    def test_hides_pending_and_rejected_problems(self):
        self.make_problem(title='Pending one', status='pending')
        self.make_problem(title='Rejected one', status='rejected')

        response = self.client.get(self.url)

        self.assertEqual(response.data['results'], [])

    def test_list_exposes_field_language_and_framework(self):
        self.make_problem(field='devops', language='golang', framework='next.js')

        row = self.client.get(self.url).data['results'][0]

        self.assertEqual(row['field'], 'devops')
        self.assertEqual(row['language'], 'golang')
        self.assertEqual(row['framework'], 'next.js')

    def test_list_does_not_leak_problem_files(self):
        problem = self.make_problem()
        ProblemFile.objects.create(problem=problem, directory='solution.py', content='secret')

        response = self.client.get(self.url)

        self.assertNotIn('files', response.data['results'][0])


class ProblemDetailViewTests(ProblemsTestCase):
    def url(self, problem_id):
        return f'/api/problems/{problem_id}/'

    def test_requires_authentication(self):
        problem = self.make_problem()
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url(problem.id)).status_code, 401)

    def test_returns_problem_with_files(self):
        problem = self.make_problem()
        ProblemFile.objects.create(problem=problem, directory='app/views.py', content='x = 1')

        response = self.client.get(self.url(problem.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Fix the cache')
        self.assertEqual(len(response.data['files']), 1)
        self.assertEqual(response.data['files'][0]['directory'], 'app/views.py')

    def test_pending_problem_is_not_visible(self):
        problem = self.make_problem(status='pending')

        self.assertEqual(self.client.get(self.url(problem.id)).status_code, 404)

    def test_unknown_id_is_404(self):
        self.assertEqual(self.client.get(self.url(uuid.uuid4())).status_code, 404)


class SubmitViewTests(ProblemsTestCase):
    def url(self, problem_id):
        return f'/api/problems/{problem_id}/submit/'

    def test_requires_authentication(self):
        problem = self.make_problem()
        self.client.force_authenticate(None)

        self.assertEqual(self.client.post(self.url(problem.id), {}, format='json').status_code, 401)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_creates_a_pending_submission(self, delay):
        problem = self.make_problem()

        response = self.client.post(
            self.url(problem.id), {'main.py': 'print(1)'}, format='json'
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['status'], 'pending')
        submission = UserDetail.objects.get()
        self.assertEqual(submission.user, self.user)
        self.assertEqual(submission.problem, problem)
        self.assertEqual(submission.status, 'pending')

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_queues_the_evaluation_task(self, delay):
        problem = self.make_problem()

        self.client.post(self.url(problem.id), {'main.py': 'print(1)'}, format='json')

        delay.assert_called_once()

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_unknown_problem_is_404(self, delay):
        response = self.client.post(self.url(uuid.uuid4()), {}, format='json')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(UserDetail.objects.count(), 0)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_submitting_to_a_pending_problem_is_rejected(self, delay):
        problem = self.make_problem(status='pending')

        response = self.client.post(
            self.url(problem.id), {'main.py': 'print(1)'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UserDetail.objects.count(), 0)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_submitting_to_a_rejected_problem_is_rejected(self, delay):
        problem = self.make_problem(status='rejected')

        response = self.client.post(
            self.url(problem.id), {'main.py': 'print(1)'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UserDetail.objects.count(), 0)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_broker_failure_rolls_the_submission_back(self, apply_async):
        from kombu.exceptions import OperationalError

        apply_async.side_effect = OperationalError('broker is down')
        problem = self.make_problem()

        response = self.client.post(
            self.url(problem.id), {'main.py': 'print(1)'}, format='json'
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(UserDetail.objects.count(), 0)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_broker_failure_leaves_no_pending_submission(self, apply_async):
        from kombu.exceptions import OperationalError

        apply_async.side_effect = OperationalError('broker is down')
        problem = self.make_problem()

        self.client.post(self.url(problem.id), {'main.py': 'print(1)'}, format='json')

        self.assertFalse(UserDetail.objects.filter(status='pending').exists())

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_time_limits_come_from_the_problem(self, apply_async):
        problem = self.make_problem(time_required=300)

        self.client.post(self.url(problem.id), {'main.py': 'print(1)'}, format='json')

        self.assertEqual(apply_async.call_args.kwargs['time_limit'], 320)
        self.assertEqual(apply_async.call_args.kwargs['soft_time_limit'], 310)


class SubmissionHistoryViewTests(ProblemsTestCase):
    url = '/api/problems/history/'

    def make_submission(self, **overrides):
        data = {
            'user': self.user, 'problem': self.make_problem(),
            'status': 'done', 'score': 70,
        }
        data.update(overrides)
        return UserDetail.objects.create(**data)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_returns_the_users_submissions(self):
        self.make_submission(score=55)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['score'], 55)

    def test_does_not_return_other_users_submissions(self):
        other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        UserDetail.objects.create(
            user=other, problem=self.make_problem(), status='done', score=99
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_newest_submission_comes_first(self):
        self.make_submission(score=10)
        self.make_submission(score=20)

        response = self.client.get(self.url)

        self.assertEqual([row['score'] for row in response.data], [20, 10])

    def test_every_submission_carries_its_problem(self):
        self.make_submission()

        response = self.client.get(self.url)

        self.assertIn('problem', response.data[0])
        self.assertIn('title', response.data[0]['problem'])


class SubmissionDetailViewTests(ProblemsTestCase):
    def url(self, submission_id):
        return f'/api/problems/{submission_id}/score/'

    def make_submission(self, **overrides):
        data = {
            'user': self.user, 'problem': self.make_problem(),
            'status': 'done', 'score': 70,
        }
        data.update(overrides)
        return UserDetail.objects.create(**data)

    def test_requires_authentication(self):
        submission = self.make_submission()
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url(submission.id)).status_code, 401)

    def test_returns_one_submission_by_id(self):
        submission = self.make_submission(score=55)

        response = self.client.get(self.url(submission.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(submission.id))
        self.assertEqual(response.data['score'], 55)

    def test_another_users_submission_is_not_reachable(self):
        other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        theirs = UserDetail.objects.create(
            user=other, problem=self.make_problem(), status='done', score=99
        )

        self.assertEqual(self.client.get(self.url(theirs.id)).status_code, 404)

    def test_unknown_id_is_404(self):
        self.assertEqual(self.client.get(self.url(uuid.uuid4())).status_code, 404)

    def test_error_message_is_not_exposed(self):
        submission = self.make_submission(status='failed', error_message='/srv/secret.py')

        response = self.client.get(self.url(submission.id))

        self.assertNotIn('error_message', response.data)
        self.assertNotIn('/srv/secret.py', str(response.data))


class ThrottleScopeTests(ProblemsTestCase):
    def rates(self):
        from django.conf import settings

        return settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']

    def test_read_view_scopes_are_configured(self):
        from problems.views import ProblemDetailView, ProblemListView, SubmitView

        for view in (ProblemListView, ProblemDetailView, SubmitView):
            with self.subTest(view=view.__name__):
                self.assertIn(view.throttle_scope, self.rates())

    def test_submission_details_scope_is_configured(self):
        from problems.views import SubmissionHistoryView

        self.assertIn(SubmissionHistoryView.throttle_scope, self.rates())


class EvaluationTaskTests(ProblemsTestCase):
    def make_submission(self, **overrides):
        data = {'user': self.user, 'problem': self.make_problem(), 'status': 'pending'}
        data.update(overrides)
        return UserDetail.objects.create(**data)

    def test_task_calls_the_evaluator_with_the_arguments_it_requires(self):
        from problems.tasks import evaluate_tasks

        submission = self.make_submission()

        with patch('problems.tasks.evaluate', autospec=True, return_value={'percentage': 90.0}):
            evaluate_tasks(submission.id, {'main.py': 'print(1)'})

        submission.refresh_from_db()
        self.assertEqual(submission.status, 'done')
        self.assertEqual(submission.score, 90)

    def test_a_container_timeout_is_reported_to_the_user(self):
        from problems.tasks import evaluate_tasks

        submission = self.make_submission()

        with patch('problems.tasks.evaluate', return_value={'percentage': 0, 'status': 'timeout'}):
            evaluate_tasks(submission.id, {})

        submission.refresh_from_db()
        self.assertEqual(submission.status, 'failed')
        self.assertEqual(submission.error_message, 'Evaluation timed out')

    def test_running_out_of_memory_is_reported_to_the_user(self):
        from problems.tasks import evaluate_tasks

        submission = self.make_submission()

        with patch(
            'problems.tasks.evaluate', return_value={'percentage': 0, 'status': 'out_of_memory'}
        ):
            evaluate_tasks(submission.id, {})

        submission.refresh_from_db()
        self.assertEqual(submission.status, 'failed')
        self.assertEqual(submission.error_message, 'Submission ran out of memory')

    def test_soft_time_limit_marks_the_submission_failed(self):
        from celery.exceptions import SoftTimeLimitExceeded

        from problems.tasks import evaluate_tasks

        submission = self.make_submission()

        with patch('problems.tasks.evaluate', side_effect=SoftTimeLimitExceeded):
            evaluate_tasks(submission.id, {})

        submission.refresh_from_db()
        self.assertEqual(submission.status, 'failed')
        self.assertEqual(submission.error_message, 'Evaluation timed out')

    def test_task_retries_when_the_submission_is_not_visible_yet(self):
        from celery.exceptions import Retry

        from problems.tasks import evaluate_tasks

        with patch.object(evaluate_tasks, 'retry', side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                evaluate_tasks(uuid.uuid4(), {})

        retry.assert_called_once()

    def test_task_does_not_evaluate_a_missing_submission(self):
        from celery.exceptions import Retry

        from problems.tasks import evaluate_tasks

        with patch('problems.tasks.evaluate') as evaluate:
            with patch.object(evaluate_tasks, 'retry', side_effect=Retry()):
                with self.assertRaises(Retry):
                    evaluate_tasks(uuid.uuid4(), {})

        evaluate.assert_not_called()

    def test_internal_errors_are_not_exposed_by_the_api(self):
        from users.serializers import UserDetailSerializer

        from problems.tasks import evaluate_tasks

        submission = self.make_submission()

        with patch('problems.tasks.evaluate', side_effect=Exception('/srv/app/secret.py line 42')):
            evaluate_tasks(submission.id, {})

        submission.refresh_from_db()
        self.assertEqual(submission.status, 'failed')

        data = UserDetailSerializer(submission).data
        self.assertNotIn('error_message', data)
        self.assertNotIn('/srv/app/secret.py', str(data))


class SubmissionValidationTests(ProblemsTestCase):
    def url(self, problem_id):
        return f'/api/problems/{problem_id}/submit/'

    def setUp(self):
        super().setUp()
        self.problem = self.make_problem()

    def submit(self, payload):
        with patch('problems.views.evaluate_tasks.apply_async') as delay:
            response = self.client.post(self.url(self.problem.id), payload, format='json')
        return response, delay

    def assertRejected(self, payload):
        response, delay = self.submit(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UserDetail.objects.count(), 0)
        delay.assert_not_called()
        return response

    def test_parent_directory_traversal_is_rejected(self):
        self.assertRejected({'../../etc/passwd': 'root'})

    def test_traversal_in_the_middle_of_a_path_is_rejected(self):
        self.assertRejected({'app/../../escape.py': 'x = 1'})

    def test_absolute_path_is_rejected(self):
        self.assertRejected({'/etc/passwd': 'root'})

    def test_backslash_separator_is_rejected(self):
        self.assertRejected({'app\\views.py': 'x = 1'})

    def test_null_byte_in_path_is_rejected(self):
        self.assertRejected({'app/\x00views.py': 'x = 1'})

    def test_overlong_path_is_rejected(self):
        self.assertRejected({'a' * 300: 'x = 1'})

    def test_empty_submission_is_rejected(self):
        self.assertRejected({})

    def test_non_object_payload_is_rejected(self):
        self.assertRejected(['main.py'])

    def test_non_string_content_is_rejected(self):
        self.assertRejected({'main.py': {'nested': 'object'}})

    def test_too_many_files_are_rejected(self):
        from django.conf import settings

        payload = {f'f{i}.py': 'x = 1' for i in range(settings.SUBMISSION_MAX_FILES + 1)}

        self.assertRejected(payload)

    def test_oversized_submission_is_rejected(self):
        from django.conf import settings

        self.assertRejected({'big.py': 'x' * (settings.SUBMISSION_MAX_TOTAL_BYTES + 1)})

    def test_nested_relative_paths_are_accepted(self):
        response, delay = self.submit({'app/core/views.py': 'x = 1', 'README.md': 'hi'})

        self.assertEqual(response.status_code, 202)
        delay.assert_called_once()

    def test_only_validated_files_reach_the_broker(self):
        response, delay = self.submit({'./app/views.py': 'x = 1'})

        self.assertEqual(response.status_code, 202)
        submission_id, files = delay.call_args.kwargs['args']
        self.assertEqual(files, {'app/views.py': 'x = 1'})
        self.assertEqual(submission_id, UserDetail.objects.get().id)


class EvaluatorSandboxTests(ProblemsTestCase):
    def evaluate(self, files, docker_mod):
        from problems.services.evaluator import evaluate

        return evaluate(files, self.make_problem().id)

    @patch('problems.services.evaluator.docker')
    def test_container_runs_with_no_network(self, docker_mod):
        self.evaluate({'main.py': 'x = 1'}, docker_mod)

        kwargs = docker_mod.from_env.return_value.containers.run.call_args.kwargs
        self.assertEqual(kwargs['network_mode'], 'none')

    @patch('problems.services.evaluator.docker')
    def test_container_keeps_memory_and_pid_limits(self, docker_mod):
        self.evaluate({'main.py': 'x = 1'}, docker_mod)

        kwargs = docker_mod.from_env.return_value.containers.run.call_args.kwargs
        self.assertEqual(kwargs['mem_limit'], '512m')
        self.assertEqual(kwargs['pids_limit'], 128)

    def test_the_run_script_never_installs_from_the_network(self):
        from problems.services.evaluator import RUN_SCRIPT

        self.assertNotIn('pip install', RUN_SCRIPT)

    @patch('problems.services.evaluator.docker')
    def test_a_submitted_requirements_file_is_not_given_to_pip(self, docker_mod):
        self.evaluate({'requirements.txt': 'requests==2.31.0'}, docker_mod)

        command = docker_mod.from_env.return_value.containers.run.call_args.args[1]
        self.assertNotIn('requirements.txt', ' '.join(command))

    @patch('problems.services.evaluator.docker')
    def test_escaping_path_never_reaches_the_filesystem(self, docker_mod):
        with self.assertRaises(ValueError):
            self.evaluate({'../escape.py': 'x = 1'}, docker_mod)

        docker_mod.from_env.return_value.containers.run.assert_not_called()

    @patch('problems.services.evaluator.docker')
    def test_absolute_path_never_reaches_the_filesystem(self, docker_mod):
        with self.assertRaises(ValueError):
            self.evaluate({'/etc/passwd': 'root'}, docker_mod)

        docker_mod.from_env.return_value.containers.run.assert_not_called()


class EvaluatorScoringTests(TestCase):
    def score(self, xml):
        from problems.services.evaluator import score_report

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


class EvaluatorContainerOutcomeTests(ProblemsTestCase):
    def evaluate(self, wait_exc=None, reload_exc=None, kill_exc=None, state=None):
        import docker as real_docker

        from problems.services.evaluator import evaluate

        container = MagicMock()
        container.attrs = {'State': state or {}}
        if wait_exc is not None:
            container.wait.side_effect = wait_exc
        if reload_exc is not None:
            container.reload.side_effect = reload_exc
        if kill_exc is not None:
            container.kill.side_effect = kill_exc

        with patch('problems.services.evaluator.docker') as docker_mod:
            docker_mod.errors = real_docker.errors
            docker_mod.from_env.return_value.containers.run.return_value = container
            return evaluate({'main.py': 'x = 1'}, self.make_problem().id), container

    def test_a_read_timeout_on_a_running_container_is_a_timeout(self):
        from requests.exceptions import ReadTimeout

        result, container = self.evaluate(
            wait_exc=ReadTimeout('timed out'), state={'Running': True}
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'timeout'})
        container.kill.assert_called_once()

    def test_a_connection_error_on_a_running_container_is_a_timeout(self):
        from requests.exceptions import ConnectionError

        result, container = self.evaluate(
            wait_exc=ConnectionError('Read timed out.'), state={'Running': True}
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'timeout'})
        container.kill.assert_called_once()

    def test_a_timed_out_container_is_removed(self):
        from requests.exceptions import ConnectionError

        _, container = self.evaluate(
            wait_exc=ConnectionError('Read timed out.'), state={'Running': True}
        )

        container.remove.assert_called_once_with(force=True)

    def test_a_kill_that_fails_does_not_break_the_timeout(self):
        import docker as real_docker
        from requests.exceptions import ConnectionError

        result, container = self.evaluate(
            wait_exc=ConnectionError('Read timed out.'),
            kill_exc=real_docker.errors.APIError('already gone'),
            state={'Running': True},
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'timeout'})
        container.remove.assert_called_once_with(force=True)

    def test_losing_the_docker_daemon_is_an_infra_error(self):
        import docker as real_docker
        from requests.exceptions import ConnectionError

        from problems.services.evaluator import ContainerInfraError

        with self.assertRaises(ContainerInfraError):
            self.evaluate(
                wait_exc=ConnectionError('daemon gone'),
                reload_exc=real_docker.errors.APIError('daemon gone'),
            )

    def test_a_container_that_finished_during_the_timeout_is_still_scored(self):
        from requests.exceptions import ConnectionError

        result, container = self.evaluate(
            wait_exc=ConnectionError('Read timed out.'), state={'Running': False}
        )

        self.assertEqual(result['status'], 'failed')
        container.kill.assert_not_called()

    def test_an_oom_killed_container_is_reported_as_out_of_memory(self):
        result, _ = self.evaluate(state={'Running': False, 'OOMKilled': True})

        self.assertEqual(result, {'percentage': 0, 'status': 'out_of_memory'})

    def test_a_missing_report_is_an_internal_failure(self):
        result, _ = self.evaluate(state={'Running': False, 'OOMKilled': False})

        self.assertEqual(result, {'percentage': 0, 'status': 'failed'})


class EvaluationBudgetTests(ProblemsTestCase):
    def test_the_container_timeout_fires_before_the_celery_limits(self):
        from problems.services.evaluator import CONTAINER_TIMEOUT_GRACE

        problem = self.make_problem(time_required=300)

        with patch('problems.views.evaluate_tasks.apply_async') as apply_async:
            self.client.post(
                f'/api/problems/{problem.id}/submit/', {'main.py': 'print(1)'}, format='json'
            )

        container_budget = problem.time_required + CONTAINER_TIMEOUT_GRACE
        soft_limit = apply_async.call_args.kwargs['soft_time_limit']
        hard_limit = apply_async.call_args.kwargs['time_limit']

        self.assertLess(container_budget, soft_limit)
        self.assertLess(soft_limit, hard_limit)


@unittest.skipUnless(
    os.environ.get('RUN_DOCKER_TESTS') == '1',
    'Needs a Docker daemon and the django-evaluator image; set RUN_DOCKER_TESTS=1.',
)
class EvaluatorLiveDockerTests(ProblemsTestCase):
    def evaluate(self, files, time_required=60):
        from problems.services.evaluator import evaluate

        return evaluate(files, self.make_problem(time_required=time_required).id)

    def running_containers(self):
        import docker

        return len(
            docker.from_env().containers.list(
                all=True, filters={'ancestor': 'django-evaluator'}
            )
        )

    def test_a_fully_passing_submission_scores_100(self):
        result = self.evaluate({'test_ok.py': 'def test_a():\n    assert 1\n'})

        self.assertEqual(result, {'percentage': 100, 'status': 'done'})

    def test_three_of_four_passing_scores_75(self):
        result = self.evaluate({
            'test_mix.py': (
                'def test_a():\n    assert 1\n'
                'def test_b():\n    assert 1\n'
                'def test_c():\n    assert 1\n'
                'def test_d():\n    assert 0\n'
            ),
        })

        self.assertEqual(result, {'percentage': 75, 'status': 'done'})

    def test_skipping_the_failing_tests_does_not_earn_the_marks(self):
        result = self.evaluate({
            'test_skip.py': (
                'import pytest\n'
                'def test_a():\n    assert 1\n'
                '@pytest.mark.skip\ndef test_b():\n    assert 0\n'
                '@pytest.mark.skip\ndef test_c():\n    assert 0\n'
                '@pytest.mark.skip\ndef test_d():\n    assert 0\n'
            ),
        })

        self.assertEqual(result, {'percentage': 25, 'status': 'done'})

    def test_a_submission_without_tests_scores_zero(self):
        result = self.evaluate({'main.py': 'x = 1\n'})

        self.assertEqual(result, {'percentage': 0, 'status': 'done'})

    def test_a_test_file_that_cannot_be_imported_scores_zero(self):
        result = self.evaluate({'test_broken.py': 'def test_a(:\n    pass\n'})

        self.assertEqual(result, {'percentage': 0, 'status': 'done'})

    def test_a_slow_submission_times_out(self):
        result = self.evaluate(
            {'test_slow.py': 'import time\ndef test_a():\n    time.sleep(60)\n'},
            time_required=0,
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'timeout'})

    def test_a_timed_out_submission_leaves_no_container_behind(self):
        before = self.running_containers()

        self.evaluate(
            {'test_slow.py': 'import time\ndef test_a():\n    time.sleep(60)\n'},
            time_required=0,
        )

        self.assertEqual(self.running_containers(), before)

    def test_a_memory_hog_is_reported_as_out_of_memory(self):
        result = self.evaluate({
            'test_mem.py': 'def test_a():\n    assert bytearray(2 * 1024 * 1024 * 1024)\n',
        })

        self.assertEqual(result, {'percentage': 0, 'status': 'out_of_memory'})

    def test_the_network_is_unreachable_from_a_submission(self):
        result = self.evaluate({
            'test_net.py': (
                'import socket\n'
                'def test_a():\n'
                '    socket.create_connection(("1.1.1.1", 80), timeout=5)\n'
            ),
        })

        self.assertEqual(result, {'percentage': 0, 'status': 'done'})

    def test_a_fork_bomb_is_contained(self):
        result = self.evaluate({
            'test_fork.py': (
                'import os\n'
                'def test_a():\n'
                '    for _ in range(300):\n'
                '        if os.fork() == 0:\n'
                '            os._exit(0)\n'
            ),
        })

        self.assertEqual(result['status'], 'done')

    def test_a_submitted_requirements_file_does_not_eat_the_time_budget(self):
        result = self.evaluate(
            {
                'requirements.txt': ''.join(f'pkg{i}==1.0.0\n' for i in range(20)),
                'test_ok.py': 'def test_a():\n    assert 1\n',
            },
            time_required=0,
        )

        self.assertEqual(result, {'percentage': 100, 'status': 'done'})
