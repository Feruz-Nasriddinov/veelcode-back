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

    def make_problem_with_hidden_tests(self, hidden=None, **overrides):
        problem = self.make_problem(**overrides)
        hidden = hidden or {'test_hidden.py': 'def test_a():\n    assert 1\n'}
        for directory, content in hidden.items():
            ProblemFile.objects.create(
                problem=problem, directory=directory, content=content, is_hidden=True
            )
        return problem


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

    def test_hidden_test_files_are_not_sent(self):
        problem = self.make_problem()
        ProblemFile.objects.create(problem=problem, directory='app/views.py', content='x = 1')
        ProblemFile.objects.create(
            problem=problem, directory='tests/test_hidden.py', content='secret', is_hidden=True
        )

        response = self.client.get(self.url(problem.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([f['directory'] for f in response.data['files']], ['app/views.py'])
        self.assertNotIn('secret', str(response.data))
        self.assertNotIn('is_hidden', response.data['files'][0])

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

    def test_a_problem_without_hidden_tests_fails_the_submission(self):
        from problems.tasks import evaluate_tasks

        submission = self.make_submission()

        with patch('problems.tasks.evaluate', return_value={'percentage': 0, 'status': 'no_tests'}):
            evaluate_tasks(submission.id, {})

        submission.refresh_from_db()
        self.assertEqual(submission.status, 'failed')
        self.assertEqual(submission.error_message, 'Problem has no hidden tests')

    def test_new_evaluator_outcomes_fail_the_submission(self):
        from problems.tasks import evaluate_tasks

        cases = {
            'unsupported': 'Unsupported problem type',
            'app_failed': 'App did not start',
        }
        for status, message in cases.items():
            with self.subTest(status=status):
                submission = self.make_submission()

                with patch('problems.tasks.evaluate', return_value={'percentage': 0, 'status': status}):
                    evaluate_tasks(submission.id, {})

                submission.refresh_from_db()
                self.assertEqual(submission.status, 'failed')
                self.assertEqual(submission.error_message, message)

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

        self.assertEqual(self.calls['runner']['mounts']['/app'], {'app.py': 'x = 1', 'conftest.py': 'evil'})
        self.assertEqual(list(self.calls['grader']['mounts']), ['/grader'])
        self.assertEqual(list(self.calls['grader']['mounts']['/grader']), ['test_hidden.py'])

    def test_hidden_tests_never_reach_the_app(self):
        self.run_evaluation({'app.py': 'x = 1'})

        self.assertNotIn('test_hidden.py', self.calls['runner']['mounts']['/app'])

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
        from requests.exceptions import ReadTimeout

        result = self.run_evaluation(
            wait_exc=ReadTimeout('timed out'), grader_state={'Running': True}
        )

        self.assertEqual(result, {'percentage': 0, 'status': 'timeout'})
        self.grader.kill.assert_called_once()
        self.runner.remove.assert_called_once_with(force=True)

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


class EvaluationBudgetTests(ProblemsTestCase):
    def test_the_container_timeout_fires_before_the_celery_limits(self):
        from problems.services.evaluators.base import CONTAINER_TIMEOUT_GRACE

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
