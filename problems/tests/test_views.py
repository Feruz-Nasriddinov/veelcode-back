import uuid
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from problems.models import ProblemFile
from users.models import User, Submission

from .base import PASSWORD, ProblemsTestCase


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

    def test_list_exposes_field_language_framework_and_source(self):
        self.make_problem(field='devops', language='golang', framework='next.js')

        row = self.client.get(self.url).data['results'][0]

        self.assertEqual(row['field'], 'devops')
        self.assertEqual(row['language'], 'golang')
        self.assertEqual(row['framework'], 'next.js')
        self.assertEqual(row['source'], 'https://github.com/acme/cache-service')

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
        self.assertEqual(response.data['source'], 'https://github.com/acme/cache-service')
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
        submission = Submission.objects.get()
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
        self.assertEqual(Submission.objects.count(), 0)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_submitting_to_a_pending_problem_is_rejected(self, delay):
        problem = self.make_problem(status='pending')

        response = self.client.post(
            self.url(problem.id), {'main.py': 'print(1)'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Submission.objects.count(), 0)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_submitting_to_a_rejected_problem_is_rejected(self, delay):
        problem = self.make_problem(status='rejected')

        response = self.client.post(
            self.url(problem.id), {'main.py': 'print(1)'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Submission.objects.count(), 0)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_broker_failure_rolls_the_submission_back(self, apply_async):
        from kombu.exceptions import OperationalError

        apply_async.side_effect = OperationalError('broker is down')
        problem = self.make_problem()

        response = self.client.post(
            self.url(problem.id), {'main.py': 'print(1)'}, format='json'
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(Submission.objects.count(), 0)

    @patch('problems.views.evaluate_tasks.apply_async')
    def test_broker_failure_leaves_no_pending_submission(self, apply_async):
        from kombu.exceptions import OperationalError

        apply_async.side_effect = OperationalError('broker is down')
        problem = self.make_problem()

        self.client.post(self.url(problem.id), {'main.py': 'print(1)'}, format='json')

        self.assertFalse(Submission.objects.filter(status='pending').exists())

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
        return Submission.objects.create(**data)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_returns_the_users_submissions(self):
        self.make_submission(score=55)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['score'], 55)

    def test_does_not_return_other_users_submissions(self):
        other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        Submission.objects.create(
            user=other, problem=self.make_problem(), status='done', score=99
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])

    def test_is_paginated(self):
        problem = self.make_problem()
        for _ in range(21):
            self.make_submission(problem=problem)

        response = self.client.get(self.url)

        self.assertEqual(response.data['count'], 21)
        self.assertEqual(len(response.data['results']), 20)
        self.assertIsNotNone(response.data['next'])

    def test_newest_submission_comes_first(self):
        self.make_submission(score=10)
        self.make_submission(score=20)

        response = self.client.get(self.url)

        self.assertEqual([row['score'] for row in response.data['results']], [20, 10])

    def test_every_submission_carries_its_problem(self):
        self.make_submission()

        response = self.client.get(self.url)

        row = response.data['results'][0]
        self.assertIn('problem', row)
        self.assertIn('title', row['problem'])


class SubmissionDetailViewTests(ProblemsTestCase):
    def url(self, submission_id):
        return f'/api/problems/{submission_id}/score/'

    def make_submission(self, **overrides):
        data = {
            'user': self.user, 'problem': self.make_problem(),
            'status': 'done', 'score': 70,
        }
        data.update(overrides)
        return Submission.objects.create(**data)

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
        theirs = Submission.objects.create(
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


class SubmitQueueLimitTests(ProblemsTestCase):
    def submit(self, problem):
        with patch('problems.views.evaluate_tasks.apply_async'):
            return self.client.post(
                f'/api/problems/{problem.id}/submit/', {'main.py': 'x = 1'}, format='json'
            )

    def test_a_user_cannot_have_more_than_two_pending_submissions(self):
        problem = self.make_problem()
        Submission.objects.create(user=self.user, problem=problem)
        Submission.objects.create(user=self.user, problem=problem)

        response = self.submit(problem)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(Submission.objects.count(), 2)

    def test_finished_submissions_do_not_count(self):
        problem = self.make_problem()
        Submission.objects.create(user=self.user, problem=problem, status='done')
        Submission.objects.create(user=self.user, problem=problem, status='failed')

        self.assertEqual(self.submit(problem).status_code, 202)

    def test_old_pending_submissions_do_not_block_forever(self):
        problem = self.make_problem()
        for _ in range(2):
            stuck = Submission.objects.create(user=self.user, problem=problem)
            Submission.objects.filter(id=stuck.id).update(
                created_at=timezone.now() - timedelta(hours=1)
            )

        self.assertEqual(self.submit(problem).status_code, 202)

    def test_the_whole_platform_is_capped(self):
        problem = self.make_problem()
        for i in range(20):
            other = User.objects.create_user(username=f'u{i}', email=f'u{i}@example.com', password=PASSWORD)
            Submission.objects.create(user=other, problem=problem)

        response = self.submit(problem)

        self.assertEqual(response.status_code, 429)
