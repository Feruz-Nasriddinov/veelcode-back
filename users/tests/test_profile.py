from unittest.mock import patch

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle

from users.views import ProfileView

from .base import UsersTestCase


class ProfileViewTests(UsersTestCase):
    url = '/api/users/profile/'

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_returns_own_submissions_with_problem_info(self):
        submission = self.make_submission(score=75)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [{
            'id': str(submission.id),
            'username': 'ryota',
            'language': 'python',
            'framework': 'django',
            'difficulty': 'medium',
            'score': 75,
            'created_at': submission.created_at.isoformat().replace('+00:00', 'Z'),
        }])

    def test_excludes_other_users_submissions(self):
        self.make_submission(user=self.other)

        response = self.client.get(self.url)

        self.assertEqual(response.data['results'], [])

    def test_query_count_does_not_grow_with_submissions(self):
        for _ in range(5):
            self.make_submission()

        with self.assertNumQueries(2):
            self.client.get(self.url)


class ProfileThrottleTests(UsersTestCase):
    url = '/api/users/profile/'

    def test_scope_has_a_configured_rate(self):
        self.assertIn(ProfileView.throttle_scope, settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])

    def test_is_throttled(self):
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {ProfileView.throttle_scope: '2/min'}):
            self.client.get(self.url)
            self.client.get(self.url)

            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 429)
