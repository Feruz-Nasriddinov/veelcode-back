from django.contrib.auth import get_user_model
from django.test import override_settings

from users.models import UserLocation

from .base import ACCESS_COOKIE, REFRESH_COOKIE, SIGNUP_URL, VALID_PASSWORD, AuthTestCase

User = get_user_model()


class SignupSuccessTests(AuthTestCase):
    def test_creates_user_and_returns_public_data_only(self):
        response = self.signup()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.data.keys()), {'id', 'username', 'email'})
        self.assertEqual(response.data['username'], 'ryota')
        self.assertEqual(response.data['email'], 'ryota@example.com')
        self.assertTrue(User.objects.filter(username='ryota').exists())

    def test_timezone_defaults_to_utc(self):
        self.signup()

        self.assertEqual(UserLocation.objects.get(user__username='ryota').timezone, 'UTC')

    def test_stores_the_given_timezone(self):
        self.signup(timezone='Asia/Tokyo')

        self.assertEqual(UserLocation.objects.get(user__username='ryota').timezone, 'Asia/Tokyo')

    def test_password_is_hashed(self):
        self.signup()
        user = User.objects.get(username='ryota')

        self.assertNotEqual(user.password, VALID_PASSWORD)
        self.assertTrue(user.check_password(VALID_PASSWORD))

    def test_logs_the_user_in_by_setting_both_cookies(self):
        response = self.signup()

        self.assertCookieSet(response, ACCESS_COOKIE)
        self.assertCookieSet(response, REFRESH_COOKIE)

    def test_cookies_are_httponly_and_samesite_lax(self):
        response = self.signup()

        for name in (ACCESS_COOKIE, REFRESH_COOKIE):
            with self.subTest(cookie=name):
                morsel = self.cookie(response, name)
                self.assertTrue(morsel['httponly'])
                self.assertEqual(morsel['samesite'], 'Lax')

    def test_cookie_paths_and_lifetimes(self):
        response = self.signup()

        access = self.cookie(response, ACCESS_COOKIE)
        self.assertEqual(access['path'], '/')
        self.assertEqual(int(access['max-age']), 10 * 60)

        refresh = self.cookie(response, REFRESH_COOKIE)
        self.assertEqual(refresh['path'], '/api/auth/')
        self.assertEqual(int(refresh['max-age']), 14 * 24 * 60 * 60)

    def test_no_token_in_response_body(self):
        response = self.signup()
        body = response.content.decode()

        self.assertNotIn('access', body)
        self.assertNotIn('refresh', body)
        self.assertNotIn(self.cookie(response, ACCESS_COOKIE).value, body)
        self.assertNotIn(self.cookie(response, REFRESH_COOKIE).value, body)

    @override_settings(AUTH_COOKIE_SECURE=False)
    def test_secure_flag_off_for_local_http_dev(self):
        response = self.signup()

        self.assertEqual(self.cookie(response, ACCESS_COOKIE)['secure'], '')

    @override_settings(AUTH_COOKIE_SECURE=True)
    def test_secure_flag_follows_the_env_setting(self):
        response = self.signup()

        for name in (ACCESS_COOKIE, REFRESH_COOKIE):
            with self.subTest(cookie=name):
                self.assertTrue(self.cookie(response, name)['secure'])


class SignupValidationTests(AuthTestCase):
    def assertRejected(self, response, field):
        self.assertEqual(response.status_code, 400)
        self.assertIn(field, response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_password_mismatch(self):
        response = self.signup(password_confirmation='SomethingElse!123')

        self.assertRejected(response, 'password_confirmation')

    def test_weak_password_is_rejected_by_django_validators(self):
        response = self.signup(password='password', password_confirmation='password')

        self.assertRejected(response, 'password')

    def test_short_password_is_rejected(self):
        response = self.signup(password='Ab1!x', password_confirmation='Ab1!x')

        self.assertRejected(response, 'password')

    def test_numeric_password_is_rejected(self):
        response = self.signup(password='9184720365', password_confirmation='9184720365')

        self.assertRejected(response, 'password')

    def test_username_may_not_contain_at_sign(self):
        response = self.signup(username='ryota@home')

        self.assertRejected(response, 'username')

    def test_invalid_email_format(self):
        response = self.signup(email='not-an-email')

        self.assertRejected(response, 'email')

    def test_unknown_timezone(self):
        response = self.signup(timezone='Mars/Olympus')

        self.assertRejected(response, 'timezone')

    def test_blank_timezone(self):
        response = self.signup(timezone='')

        self.assertRejected(response, 'timezone')

    def test_timezone_path_traversal_is_rejected(self):
        response = self.signup(timezone='../../etc/passwd')

        self.assertRejected(response, 'timezone')

    def test_missing_fields(self):
        response = self.client.post(SIGNUP_URL, {'username': 'ryota'}, format='json')

        self.assertEqual(response.status_code, 400)
        for field in ('email', 'password', 'password_confirmation'):
            self.assertIn(field, response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_empty_payload(self):
        response = self.client.post(SIGNUP_URL, {}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)


class SignupUniquenessTests(AuthTestCase):
    def test_duplicate_email_different_casing(self):
        self.create_user(username='taken', email='ryota@example.com')

        response = self.signup(email='RYOTA@Example.COM')

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_username_different_casing(self):
        self.create_user(username='ryota', email='taken@example.com')

        response = self.signup(username='RyOtA')

        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_database_rejects_case_insensitive_duplicates(self):
        from django.db import IntegrityError, transaction

        self.create_user(username='ryota', email='ryota@example.com')

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                username='RYOTA', email='other@example.com', password=VALID_PASSWORD
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                username='other', email='RYOTA@EXAMPLE.COM', password=VALID_PASSWORD
            )
