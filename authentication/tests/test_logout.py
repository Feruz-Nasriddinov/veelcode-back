from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from .base import ACCESS_COOKIE, LOGOUT_URL, REFRESH_COOKIE, REFRESH_URL, AuthTestCase


class LogoutTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(username='ryota', email='ryota@example.com')
        login = self.login()
        self.refresh_value = self.cookie(login, REFRESH_COOKIE).value

    def logout(self):
        return self.client.post(LOGOUT_URL, format='json')

    def test_blacklists_the_refresh_token(self):
        jti = RefreshToken(self.refresh_value).payload['jti']

        response = self.logout()

        self.assertEqual(response.status_code, 204)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=jti).exists())

    def test_clears_both_cookies(self):
        response = self.logout()

        self.assertCookieCleared(response, ACCESS_COOKIE)
        self.assertCookieCleared(response, REFRESH_COOKIE)

    def test_cleared_cookies_keep_their_original_paths(self):
        response = self.logout()

        self.assertEqual(self.cookie(response, ACCESS_COOKIE)['path'], '/')
        self.assertEqual(self.cookie(response, REFRESH_COOKIE)['path'], '/api/auth/')

    def test_refresh_token_is_unusable_after_logout(self):
        self.logout()

        self.client.cookies[REFRESH_COOKIE] = self.refresh_value
        response = self.client.post(REFRESH_URL, format='json')

        self.assertEqual(response.status_code, 401)

    def test_works_with_no_cookie_at_all(self):
        self.client.cookies.clear()

        response = self.logout()

        self.assertEqual(response.status_code, 204)
        self.assertCookieCleared(response, ACCESS_COOKIE)
        self.assertCookieCleared(response, REFRESH_COOKIE)

    def test_works_with_a_malformed_cookie(self):
        self.client.cookies[REFRESH_COOKIE] = 'not-a-jwt'

        response = self.logout()

        self.assertEqual(response.status_code, 204)

    def test_works_when_already_logged_out(self):
        self.logout()
        self.client.cookies[REFRESH_COOKIE] = self.refresh_value

        response = self.logout()

        self.assertEqual(response.status_code, 204)
