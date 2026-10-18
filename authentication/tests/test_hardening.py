from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User

from .base import ACCESS_COOKIE, LOGIN_URL, LOGOUT_URL, ME_URL, REFRESH_COOKIE, REFRESH_URL, AuthTestCase


class LoggedOutAccessTokenTests(AuthTestCase):
    def test_access_token_stops_working_after_logout(self):
        self.create_user()
        login = self.login()
        access = self.cookie(login, ACCESS_COOKIE).value
        self.assertEqual(self.client.get(ME_URL).status_code, 200)

        self.client.post(LOGOUT_URL, format='json')
        self.client.cookies[ACCESS_COOKIE] = access

        self.assertEqual(self.client.get(ME_URL).status_code, 401)


class RefreshReuseTests(AuthTestCase):
    def test_replaying_a_rotated_refresh_token_revokes_every_session(self):
        user = self.create_user()
        old = self.cookie(self.login(), REFRESH_COOKIE).value
        rotated = self.client.post(REFRESH_URL, format='json')
        newest = self.cookie(rotated, REFRESH_COOKIE).value

        self.client.cookies[REFRESH_COOKIE] = old
        replay = self.client.post(REFRESH_URL, format='json')
        self.client.cookies[REFRESH_COOKIE] = newest
        after = self.client.post(REFRESH_URL, format='json')

        self.assertEqual(replay.status_code, 401)
        self.assertEqual(after.status_code, 401)
        self.assertTrue(BlacklistedToken.objects.filter(token__user=user).exists())

    def test_a_token_that_loses_the_blacklist_race_is_refused(self):
        from authentication import services

        user = self.create_user()
        raw = str(RefreshToken.for_user(user))
        RefreshToken(raw).blacklist()
        token = RefreshToken(raw, verify=False)

        with self.assertRaises(TokenError):
            services.rotate_refresh_token(str(token))


class SpoofedForwardedForTests(AuthTestCase):
    @patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'auth-login': '2/min'})
    def test_changing_the_header_does_not_reset_the_login_limit(self):
        statuses = [
            self.client.post(
                LOGIN_URL, {'identifier': 'x', 'password': 'y'}, format='json',
                HTTP_X_FORWARDED_FOR=f'1.2.3.{i}, 9.9.9.9',
            ).status_code
            for i in range(4)
        ]

        self.assertEqual(statuses[-1], 429)


class RequestSizeLimitTests(TestCase):
    @override_settings(REQUEST_MAX_BYTES=100)
    def test_oversized_body_is_refused_before_parsing(self):
        response = APIClient().post(LOGIN_URL, 'x' * 500, content_type='application/json')

        self.assertEqual(response.status_code, 413)

    def test_normal_body_passes(self):
        response = APIClient().post(LOGIN_URL, {'identifier': 'a', 'password': 'b'}, format='json')

        self.assertEqual(response.status_code, 401)


class AdminLoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_admin_login_is_limited_per_ip(self):
        statuses = [
            self.client.post('/admin/login/', {'username': 'a', 'password': 'b'}).status_code
            for _ in range(7)
        ]

        self.assertNotIn(429, statuses[:5])
        self.assertEqual(statuses[-1], 429)

    def test_admin_login_page_still_loads(self):
        self.assertEqual(self.client.get('/admin/login/').status_code, 200)


class ApiDocsAccessTests(TestCase):
    def test_schema_is_closed_to_anonymous_and_normal_users(self):
        self.assertIn(APIClient().get('/api/schema').status_code, (401, 403))
        user = User.objects.create_user(username='u', email='u@example.com', password='Sup3rSecret!pass')
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.get('/api/schema').status_code, 403)

    def test_schema_is_open_to_staff(self):
        admin = User.objects.create_user(
            username='a', email='a@example.com', password='Sup3rSecret!pass', is_staff=True
        )
        client = APIClient()
        client.force_authenticate(admin)
        self.assertEqual(client.get('/api/schema').status_code, 200)


class FlushTokensTaskTests(TestCase):
    def test_task_runs_the_flush_command(self):
        from authentication.tasks import flush_expired_tokens

        with patch('authentication.tasks.call_command') as call:
            flush_expired_tokens()

        call.assert_called_once_with('flushexpiredtokens')
