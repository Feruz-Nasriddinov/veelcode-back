from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from .base import ACCESS_COOKIE, ME_URL, AuthTestCase


class MeTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(username='ryota', email='ryota@example.com')

    def test_authenticated_returns_the_current_user(self):
        self.login()

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {'id': self.user.id, 'username': 'ryota', 'email': 'ryota@example.com'},
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 401)

    def test_authorization_header_is_ignored(self):
        token = AccessToken.for_user(self.user)

        response = self.client.get(ME_URL, HTTP_AUTHORIZATION=f'Bearer {token}')

        self.assertEqual(response.status_code, 401)

    def test_expired_access_token_is_rejected(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(
            from_time=timezone.now() - timedelta(hours=1),
            lifetime=timedelta(minutes=10),
        )
        self.client.cookies[ACCESS_COOKIE] = str(token)

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 401)

    def test_malformed_access_token_is_rejected(self):
        self.client.cookies[ACCESS_COOKIE] = 'not-a-jwt'

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 401)

    def test_token_signed_with_another_key_is_rejected(self):
        import jwt

        payload = dict(AccessToken.for_user(self.user).payload)
        attacker_key = 'attacker-key-long-enough-to-avoid-a-pyjwt-length-warning'
        self.client.cookies[ACCESS_COOKIE] = jwt.encode(payload, attacker_key, algorithm='HS256')

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 401)

    def test_access_cookie_still_works_after_logout_is_not_possible(self):
        self.login()
        self.client.post('/api/auth/logout/', format='json')

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 401)
