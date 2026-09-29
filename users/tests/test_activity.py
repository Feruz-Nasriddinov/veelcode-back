from unittest.mock import patch

from django.conf import settings
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from users.models import UserLocation
from users.views import MIN_YEAR, ActivityView

from .base import UsersTestCase


class ActivityViewTests(UsersTestCase):
    url = '/api/users/profile/activity/'

    def setUp(self):
        super().setUp()
        self.year = timezone.localdate().year

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_empty_year(self):
        response = self.client.get(self.url, {'year': self.year})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'year': self.year, 'total': 0, 'days': []})

    def test_defaults_to_current_year(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['year'], self.year)

    def test_groups_submissions_by_day_in_order(self):
        self.make_submission(created_at=self.aware(self.year, 3, 2, 23, 59))
        self.make_submission(created_at=self.aware(self.year, 1, 1, 0, 0))
        self.make_submission(created_at=self.aware(self.year, 3, 2, 8, 0))

        response = self.client.get(self.url, {'year': self.year})

        self.assertEqual(response.data, {
            'year': self.year,
            'total': 3,
            'days': [
                {'date': f'{self.year}-01-01', 'count': 1},
                {'date': f'{self.year}-03-02', 'count': 2},
            ],
        })

    def test_excludes_other_years_and_other_users(self):
        self.make_submission(created_at=self.aware(self.year - 1, 12, 31, 23, 59))
        self.make_submission(created_at=self.aware(self.year + 1, 1, 1, 0, 0))
        self.make_submission(user=self.other, created_at=self.aware(self.year, 5, 5, 12, 0))

        response = self.client.get(self.url, {'year': self.year})

        self.assertEqual(response.data['total'], 0)

    def test_non_numeric_year_is_rejected(self):
        response = self.client.get(self.url, {'year': 'abc'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'detail': 'year must be a number'})

    def test_year_before_minimum_is_rejected(self):
        response = self.client.get(self.url, {'year': MIN_YEAR - 1})

        self.assertEqual(response.status_code, 400)

    def test_future_year_is_rejected(self):
        response = self.client.get(self.url, {'year': self.year + 1})

        self.assertEqual(response.status_code, 400)


class ActivityTimezoneTests(UsersTestCase):
    url = '/api/users/profile/activity/'

    def test_days_use_the_users_timezone(self):
        UserLocation.objects.create(user=self.user, timezone='Asia/Tokyo')
        self.make_submission(created_at=self.aware(2026, 3, 1, 16, 0))

        response = self.client.get(self.url, {'year': 2026})

        self.assertEqual(response.data['days'], [{'date': '2026-03-02', 'count': 1}])

    def test_year_boundaries_use_the_users_timezone(self):
        UserLocation.objects.create(user=self.user, timezone='Asia/Tokyo')
        self.make_submission(created_at=self.aware(2025, 12, 31, 16, 0))

        response = self.client.get(self.url, {'year': 2026})

        self.assertEqual(response.data['days'], [{'date': '2026-01-01', 'count': 1}])

    def test_no_location_uses_utc(self):
        self.make_submission(created_at=self.aware(2026, 3, 1, 16, 0))

        response = self.client.get(self.url, {'year': 2026})

        self.assertEqual(response.data['days'], [{'date': '2026-03-01', 'count': 1}])

    def test_invalid_timezone_falls_back_to_utc(self):
        UserLocation.objects.create(user=self.user, timezone='Not/AZone')
        self.make_submission(created_at=self.aware(2026, 3, 1, 16, 0))

        response = self.client.get(self.url, {'year': 2026})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['days'], [{'date': '2026-03-01', 'count': 1}])


class ActivityThrottleTests(UsersTestCase):
    url = '/api/users/profile/activity/'

    def test_scope_has_a_configured_rate(self):
        self.assertIn(ActivityView.throttle_scope, settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])

    def test_is_throttled(self):
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {ActivityView.throttle_scope: '2/min'}):
            self.client.get(self.url)
            self.client.get(self.url)

            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 429)
