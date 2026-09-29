import uuid
from unittest.mock import patch

from users.models import Submission

from .base import ProblemsTestCase


class EvaluationTaskTests(ProblemsTestCase):
    def make_submission(self, **overrides):
        data = {'user': self.user, 'problem': self.make_problem(), 'status': 'pending'}
        data.update(overrides)
        return Submission.objects.create(**data)

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
