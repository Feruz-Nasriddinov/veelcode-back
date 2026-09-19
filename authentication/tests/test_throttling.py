from unittest.mock import patch

from rest_framework.throttling import ScopedRateThrottle

from .base import REFRESH_URL, SIGNUP_URL, AuthTestCase

THROTTLED_RATES = {
    'auth-signup': '2/hour',
    'auth-login': '2/min',
    'auth-refresh': '2/min',
}


def with_rates():
    return patch.dict(ScopedRateThrottle.THROTTLE_RATES, THROTTLED_RATES)


class ThrottlingTests(AuthTestCase):
    @with_rates()
    def test_signup_is_throttled(self):
        self.signup(username='one', email='one@example.com')
        self.signup(username='two', email='two@example.com')

        response = self.signup(username='three', email='three@example.com')

        self.assertEqual(response.status_code, 429)

    @with_rates()
    def test_login_is_throttled(self):
        self.create_user(username='ryota', email='ryota@example.com')
        self.login(password='WrongPassword!1')
        self.login(password='WrongPassword!1')

        response = self.login()

        self.assertEqual(response.status_code, 429)

    @with_rates()
    def test_refresh_is_throttled(self):
        self.create_user(username='ryota', email='ryota@example.com')
        self.login()
        self.client.post(REFRESH_URL, format='json')
        self.client.post(REFRESH_URL, format='json')

        response = self.client.post(REFRESH_URL, format='json')

        self.assertEqual(response.status_code, 429)

    def test_default_rates_do_not_throttle_normal_use(self):
        self.create_user(username='ryota', email='ryota@example.com')

        for _ in range(3):
            self.assertEqual(self.login().status_code, 200)

    def test_each_endpoint_has_its_own_counter(self):
        self.create_user(username='ryota', email='ryota@example.com')
        for _ in range(3):
            self.login()

        response = self.client.post(
            SIGNUP_URL, self.signup_payload(username='fresh', email='fresh@example.com'),
            format='json',
        )

        self.assertEqual(response.status_code, 201)


class ThrottleConfigTests(AuthTestCase):
    def test_all_auth_scopes_have_a_configured_rate(self):
        from django.conf import settings

        from authentication.views import LoginView, RefreshView, SignupView

        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        for view in (SignupView, LoginView, RefreshView):
            with self.subTest(view=view.__name__):
                scope = getattr(view, 'throttle_scope', None)
                self.assertIsNotNone(scope, f'{view.__name__} has no throttle_scope')
                self.assertIn(scope, rates)
