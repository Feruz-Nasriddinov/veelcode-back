from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from config.testing import SecureAPIClient

User = get_user_model()

ACCESS_COOKIE = 'access_token'
REFRESH_COOKIE = 'refresh_token'

SIGNUP_URL = '/api/auth/signup/'
LOGIN_URL = '/api/auth/login/'
REFRESH_URL = '/api/auth/refresh/'
LOGOUT_URL = '/api/auth/logout/'
ME_URL = '/api/auth/me/'
CSRF_URL = '/api/auth/csrf/'
GOOGLE_URL = '/api/auth/google/'
GITHUB_URL = '/api/auth/github/'
OAUTH_STATE_URL = '/api/auth/oauth-state/'

VALID_PASSWORD = 'Sup3rSecret!pass'


class AuthTestCase(TestCase):
    client_class = SecureAPIClient

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def signup_payload(self, **overrides):
        payload = {
            'username': 'ryota',
            'email': 'ryota@example.com',
            'password': VALID_PASSWORD,
            'password_confirmation': VALID_PASSWORD,
        }
        payload.update(overrides)
        return payload

    def signup(self, **overrides):
        return self.client.post(SIGNUP_URL, self.signup_payload(**overrides), format='json')

    def create_user(self, username='ryota', email='ryota@example.com', password=VALID_PASSWORD):
        return User.objects.create_user(username=username, email=email, password=password)

    def login(self, identifier='ryota', password=VALID_PASSWORD):
        return self.client.post(
            LOGIN_URL, {'identifier': identifier, 'password': password}, format='json'
        )

    def social_login(self, url=GOOGLE_URL, code='auth-code', state=None):
        if state is None:
            state = self.client.get(OAUTH_STATE_URL).data['state']
        return self.client.post(url, {'code': code, 'state': state}, format='json')

    def cookie(self, response, name):
        return response.cookies.get(name)

    def assertCookieSet(self, response, name):
        morsel = self.cookie(response, name)
        self.assertIsNotNone(morsel, f'expected cookie {name!r} to be set')
        self.assertNotEqual(morsel.value, '', f'expected cookie {name!r} to have a value')
        return morsel

    def assertCookieCleared(self, response, name):
        morsel = self.cookie(response, name)
        self.assertIsNotNone(morsel, f'expected cookie {name!r} to be overwritten')
        self.assertEqual(morsel.value, '')
        self.assertEqual(str(morsel['max-age']), '0')
