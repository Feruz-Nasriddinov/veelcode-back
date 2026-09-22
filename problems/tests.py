import uuid
from unittest.mock import patch

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


class SubmissionDetailsViewTests(ProblemsTestCase):
    url = '/api/problems/score/'

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

    def test_soft_time_limit_marks_the_submission_failed(self):
        from celery.exceptions import SoftTimeLimitExceeded

        from problems.tasks import evaluate_tasks

        submission = self.make_submission()

        with patch('problems.tasks.evaluate', side_effect=SoftTimeLimitExceeded):
            evaluate_tasks(submission.id, {})

        submission.refresh_from_db()
        self.assertEqual(submission.status, 'failed')
        self.assertEqual(submission.error_message, 'Evaluation timed out')

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
