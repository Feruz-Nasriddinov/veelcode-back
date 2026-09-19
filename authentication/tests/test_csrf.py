from django.test import override_settings
from rest_framework.test import APIClient

from .base import (
    CSRF_URL,
    LOGIN_URL,
    LOGOUT_URL,
    REFRESH_COOKIE,
    REFRESH_URL,
    SIGNUP_URL,
    VALID_PASSWORD,
    AuthTestCase,
)

PROBE_URL = '/api/probe/'


class EnforcingClientMixin:
    def setUp(self):
        super().setUp()
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_token(self):
        self.client.get(CSRF_URL)
        return self.client.cookies['csrftoken'].value

    def post(self, url, payload=None, token=None):
        extra = {'HTTP_X_CSRFTOKEN': token} if token is not None else {}
        return self.client.post(url, payload or {}, format='json', **extra)


@override_settings(ROOT_URLCONF='authentication.tests.csrf_urls')
class CsrfEnforcementTests(EnforcingClientMixin, AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(username='ryota', email='ryota@example.com')
        self.post(
            LOGIN_URL,
            {'identifier': 'ryota', 'password': VALID_PASSWORD},
            token=self.csrf_token(),
        )

    def test_post_with_cookie_auth_and_no_csrf_token_is_rejected(self):
        response = self.post(PROBE_URL)

        self.assertEqual(response.status_code, 403)
        self.assertIn('CSRF', str(response.data['detail']))

    def test_post_with_a_valid_csrf_token_succeeds(self):
        response = self.post(PROBE_URL, token=self.csrf_token())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user'], 'ryota')

    def test_post_with_a_wrong_csrf_token_is_rejected(self):
        self.csrf_token()

        response = self.post(PROBE_URL, token='bogus')

        self.assertEqual(response.status_code, 403)

    def test_safe_methods_do_not_require_a_csrf_token(self):
        response = self.client.get(PROBE_URL)

        self.assertEqual(response.status_code, 200)

    def test_unsafe_methods_all_require_a_csrf_token(self):
        for method in ('put', 'patch', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(PROBE_URL, {}, format='json')
                self.assertEqual(response.status_code, 403)


class PublicEndpointCsrfTests(EnforcingClientMixin, AuthTestCase):
    def test_signup_without_a_csrf_token_is_rejected(self):
        response = self.post(SIGNUP_URL, self.signup_payload())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.user_count(), 0)

    def test_signup_with_a_csrf_token_succeeds(self):
        response = self.post(SIGNUP_URL, self.signup_payload(), token=self.csrf_token())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.user_count(), 1)

    def test_login_without_a_csrf_token_is_rejected(self):
        self.create_user(username='ryota', email='ryota@example.com')

        response = self.post(LOGIN_URL, {'identifier': 'ryota', 'password': VALID_PASSWORD})

        self.assertEqual(response.status_code, 403)

    def test_login_with_a_csrf_token_succeeds(self):
        self.create_user(username='ryota', email='ryota@example.com')

        response = self.post(
            LOGIN_URL,
            {'identifier': 'ryota', 'password': VALID_PASSWORD},
            token=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 200)

    def test_refresh_without_a_csrf_token_is_rejected(self):
        self.create_user(username='ryota', email='ryota@example.com')
        token = self.csrf_token()
        self.post(LOGIN_URL, {'identifier': 'ryota', 'password': VALID_PASSWORD}, token=token)
        before = self.client.cookies[REFRESH_COOKIE].value

        response = self.post(REFRESH_URL)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.cookies[REFRESH_COOKIE].value, before)

    def test_refresh_with_a_csrf_token_succeeds(self):
        self.create_user(username='ryota', email='ryota@example.com')
        token = self.csrf_token()
        self.post(LOGIN_URL, {'identifier': 'ryota', 'password': VALID_PASSWORD}, token=token)

        response = self.post(REFRESH_URL, token=self.csrf_token())

        self.assertEqual(response.status_code, 200)

    def test_logout_without_a_csrf_token_is_rejected(self):
        response = self.post(LOGOUT_URL)

        self.assertEqual(response.status_code, 403)

    def test_logout_with_a_csrf_token_succeeds(self):
        response = self.post(LOGOUT_URL, token=self.csrf_token())

        self.assertEqual(response.status_code, 204)

    def user_count(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.count()


class CsrfEndpointTests(AuthTestCase):
    def test_csrf_endpoint_sets_the_cookie(self):
        response = self.client.get(CSRF_URL)

        self.assertEqual(response.status_code, 204)
        self.assertIn('csrftoken', response.cookies)
        self.assertNotEqual(response.cookies['csrftoken'].value, '')

    def test_csrf_cookie_is_readable_by_javascript(self):
        response = self.client.get(CSRF_URL)

        self.assertEqual(response.cookies['csrftoken']['httponly'], '')

    def test_csrf_endpoint_works_when_logged_out(self):
        response = self.client.get(CSRF_URL)

        self.assertEqual(response.status_code, 204)
