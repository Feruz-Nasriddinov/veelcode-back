from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from .base import ACCESS_COOKIE, REFRESH_COOKIE, REFRESH_URL, AuthTestCase


class RefreshTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(username='ryota', email='ryota@example.com')
        login = self.login()
        self.original_refresh = self.cookie(login, REFRESH_COOKIE).value
        self.original_access = self.cookie(login, ACCESS_COOKIE).value

    def refresh(self):
        return self.client.post(REFRESH_URL, format='json')

    def test_success_issues_new_cookies(self):
        response = self.refresh()

        self.assertEqual(response.status_code, 200)
        self.assertCookieSet(response, ACCESS_COOKIE)
        self.assertCookieSet(response, REFRESH_COOKIE)
        self.assertEqual(response.data['id'], self.user.id)

    def test_refresh_token_is_rotated(self):
        response = self.refresh()

        self.assertNotEqual(self.cookie(response, REFRESH_COOKIE).value, self.original_refresh)

    def test_old_refresh_token_is_blacklisted_after_rotation(self):
        old_jti = RefreshToken(self.original_refresh).payload['jti']

        self.refresh()

        self.assertTrue(BlacklistedToken.objects.filter(token__jti=old_jti).exists())

    def test_reusing_the_old_refresh_token_fails(self):
        self.refresh()

        self.client.cookies[REFRESH_COOKIE] = self.original_refresh
        response = self.refresh()

        self.assertEqual(response.status_code, 401)

    def test_replay_clears_the_cookies(self):
        self.refresh()
        self.client.cookies[REFRESH_COOKIE] = self.original_refresh

        response = self.refresh()

        self.assertCookieCleared(response, ACCESS_COOKIE)
        self.assertCookieCleared(response, REFRESH_COOKIE)

    def test_rotated_token_can_itself_be_used_once(self):
        first = self.refresh()
        self.assertEqual(first.status_code, 200)

        second = self.refresh()
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(
            self.cookie(second, REFRESH_COOKIE).value,
            self.cookie(first, REFRESH_COOKIE).value,
        )

    def test_missing_cookie_fails(self):
        self.client.cookies.clear()

        response = self.refresh()

        self.assertEqual(response.status_code, 401)

    def test_malformed_cookie_fails(self):
        self.client.cookies[REFRESH_COOKIE] = 'not-a-jwt'

        response = self.refresh()

        self.assertEqual(response.status_code, 401)

    def test_access_token_is_not_accepted_as_a_refresh_token(self):
        self.client.cookies[REFRESH_COOKIE] = self.original_access

        response = self.refresh()

        self.assertEqual(response.status_code, 401)

    def test_no_token_in_response_body(self):
        response = self.refresh()
        body = response.content.decode()

        self.assertNotIn(self.cookie(response, ACCESS_COOKIE).value, body)
        self.assertNotIn(self.cookie(response, REFRESH_COOKIE).value, body)

    def test_refresh_for_deleted_user_fails(self):
        self.user.delete()

        response = self.refresh()

        self.assertEqual(response.status_code, 401)
