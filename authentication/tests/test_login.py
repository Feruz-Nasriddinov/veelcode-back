from .base import ACCESS_COOKIE, LOGIN_URL, REFRESH_COOKIE, VALID_PASSWORD, AuthTestCase

GENERIC_ERROR = 'Invalid credentials'


class LoginSuccessTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(username='ryota', email='ryota@example.com')

    def test_login_by_username(self):
        response = self.login(identifier='ryota')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.user.id)

    def test_login_by_email(self):
        response = self.login(identifier='ryota@example.com')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.user.id)

    def test_username_is_case_insensitive(self):
        response = self.login(identifier='RyOtA')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.user.id)

    def test_email_is_case_insensitive(self):
        response = self.login(identifier='RYOTA@Example.COM')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.user.id)

    def test_sets_both_cookies(self):
        response = self.login()

        self.assertCookieSet(response, ACCESS_COOKIE)
        self.assertCookieSet(response, REFRESH_COOKIE)
        self.assertTrue(self.cookie(response, ACCESS_COOKIE)['httponly'])
        self.assertEqual(self.cookie(response, REFRESH_COOKIE)['samesite'], 'Lax')

    def test_returns_public_data_only(self):
        response = self.login()

        self.assertEqual(set(response.data.keys()), {'id', 'username', 'email'})

    def test_no_token_in_response_body(self):
        response = self.login()
        body = response.content.decode()

        self.assertNotIn('access', body)
        self.assertNotIn('refresh', body)
        self.assertNotIn('token', body)
        self.assertNotIn(self.cookie(response, ACCESS_COOKIE).value, body)
        self.assertNotIn(self.cookie(response, REFRESH_COOKIE).value, body)


class LoginFailureTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.create_user(username='ryota', email='ryota@example.com')

    def assertGenericFailure(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data['detail'], GENERIC_ERROR)
        self.assertNotIn(ACCESS_COOKIE, response.cookies)
        self.assertNotIn(REFRESH_COOKIE, response.cookies)

    def test_wrong_password(self):
        self.assertGenericFailure(self.login(password='WrongPassword!1'))

    def test_nonexistent_username_gives_the_same_error(self):
        wrong_password = self.login(password='WrongPassword!1')
        no_such_user = self.login(identifier='nobody', password=VALID_PASSWORD)

        self.assertGenericFailure(no_such_user)
        self.assertEqual(no_such_user.data, wrong_password.data)
        self.assertEqual(no_such_user.status_code, wrong_password.status_code)

    def test_nonexistent_email_gives_the_same_error(self):
        wrong_password = self.login(password='WrongPassword!1')
        no_such_user = self.login(identifier='nobody@example.com', password=VALID_PASSWORD)

        self.assertGenericFailure(no_such_user)
        self.assertEqual(no_such_user.data, wrong_password.data)

    def test_error_never_names_the_field_that_failed(self):
        body = self.login(password='WrongPassword!1').content.decode().lower()

        for leak in ('username', 'email', 'exist', 'not found', 'password'):
            self.assertNotIn(leak, body)

    def test_inactive_user_is_rejected(self):
        user = self.create_user(username='dormant', email='dormant@example.com')
        user.is_active = False
        user.save(update_fields=['is_active'])

        self.assertGenericFailure(self.login(identifier='dormant'))

    def test_missing_fields(self):
        response = self.client.post(LOGIN_URL, {'identifier': 'ryota'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data)
