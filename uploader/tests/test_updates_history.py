import uuid
from unittest.mock import patch

from rest_framework.throttling import ScopedRateThrottle

from problems.models import Problem, ProblemFile, UpdateProblem
from users.models import User
from uploader.views import UpdatesHistoryView

from .base import PASSWORD, UploaderTestCase

HISTORY_URL = '/api/uploader/history/'


class UpdatesHistoryViewTests(UploaderTestCase):
    def make_update(self, author, title, **overrides):
        problem = Problem.objects.create(
            title=f'{title} problem', description='x', difficulty='easy',
            status='pending', created_by=author,
            field='backend', language='python', framework='django',
        )
        problem_file = ProblemFile.objects.create(problem=problem, directory='app/views.py', content='x = 1')
        return UpdateProblem.objects.create(
            title=title, problem=problem, problem_file=problem_file, new_content='x = 2', **overrides
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, 401)

    def test_lists_only_updates_to_your_own_problems(self):
        mine = self.make_update(self.user, 'Mine')
        other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        self.make_update(other, 'Theirs')

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual(row['id'], str(mine.id))
        self.assertEqual(row['title'], 'Mine')
        self.assertEqual(row['status'], 'pending')
        self.assertEqual(row['created_at'], mine.created_at.isoformat().replace('+00:00', 'Z'))
        self.assertEqual(row['problem']['id'], str(mine.problem.id))
        self.assertEqual(row['problem_file']['id'], str(mine.problem_file.id))

    def test_empty_when_you_have_no_updates(self):
        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])

    def test_is_paginated(self):
        for number in range(21):
            self.make_update(self.user, f'Update {number}')

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.data['count'], 21)
        self.assertEqual(len(response.data['results']), 20)
        self.assertIsNotNone(response.data['next'])

    def test_newest_update_comes_first(self):
        self.make_update(self.user, 'Older')
        self.make_update(self.user, 'Newer')

        response = self.client.get(HISTORY_URL)

        self.assertEqual([row['title'] for row in response.data['results']], ['Newer', 'Older'])

    def test_same_timestamp_falls_back_to_id(self):
        first = self.make_update(self.user, 'Lower id', id=uuid.UUID(int=1))
        self.make_update(self.user, 'Higher id', id=uuid.UUID(int=2))
        UpdateProblem.objects.update(created_at=first.created_at)

        response = self.client.get(HISTORY_URL)

        self.assertEqual([row['title'] for row in response.data['results']], ['Higher id', 'Lower id'])

    def test_query_count_does_not_grow_with_rows(self):
        self.make_update(self.user, 'First')
        self.make_update(self.user, 'Second')

        with self.assertNumQueries(2):
            self.client.get(HISTORY_URL)

    def test_is_throttled(self):
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {UpdatesHistoryView.throttle_scope: '2/min'}):
            self.client.get(HISTORY_URL)
            self.client.get(HISTORY_URL)
            response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, 429)
