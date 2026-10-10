from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import override_settings

from users.models import SocialAccount, UserLocation

from .base import (
    ACCESS_COOKIE,
    GITHUB_URL,
    GOOGLE_URL,
    REFRESH_COOKIE,
    VALID_PASSWORD,
    AuthTestCase,
)

User = get_user_model()

GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
GITHUB_USER_URL = 'https://api.github.com/user'
GITHUB_EMAILS_URL = 'https://api.github.com/user/emails'

OAUTH_SETTINGS = {
    'GOOGLE_OAUTH_CLIENT_ID': 'google-client-id',
    'GOOGLE_OAUTH_CLIENT_SECRET': 'google-client-secret',
    'GOOGLE_OAUTH_REDIRECT_URI': 'http://localhost:3000/auth/google/callback',
    'GITHUB_OAUTH_CLIENT_ID': 'github-client-id',
    'GITHUB_OAUTH_CLIENT_SECRET': 'github-client-secret',
    'GITHUB_OAUTH_REDIRECT_URI': 'http://localhost:3000/auth/github/callback',
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        if self.payload is None:
            raise ValueError('not json')
        return self.payload


@override_settings(**OAUTH_SETTINGS)
class SocialLoginTestCase(AuthTestCase):
    def mock_provider(self, routes):
        def fake_request(method, url, **kwargs):
            self.assertIn(url, routes, f'unexpected request to {url}')
            result = routes[url]
            if isinstance(result, Exception):
                raise result
            if isinstance(result, FakeResponse):
                return result
            return FakeResponse(result)

        patcher = patch('authentication.oauth.requests.request', side_effect=fake_request)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def google_routes(self, **overrides):
        routes = {
            GOOGLE_TOKEN_URL: {'access_token': 'google-access-token'},
            GOOGLE_USERINFO_URL: {
                'sub': '1234567890',
                'email': 'ryota@example.com',
                'email_verified': True,
            },
        }
        routes.update(overrides)
        return routes

    def github_routes(self, **overrides):
        routes = {
            GITHUB_TOKEN_URL: {'access_token': 'github-access-token'},
            GITHUB_USER_URL: {'id': 42, 'login': 'ryota'},
            GITHUB_EMAILS_URL: [
                {'email': 'other@example.com', 'primary': False, 'verified': True},
                {'email': 'ryota@example.com', 'primary': True, 'verified': True},
            ],
        }
        routes.update(overrides)
        return routes


class GoogleLoginSuccessTests(SocialLoginTestCase):
    def test_creates_user_and_sets_cookies(self):
        self.mock_provider(self.google_routes())

        response = self.social_login(GOOGLE_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data.keys()), {'id', 'username', 'email'})
        self.assertEqual(response.data['email'], 'ryota@example.com')
        self.assertCookieSet(response, ACCESS_COOKIE)
        self.assertCookieSet(response, REFRESH_COOKIE)

    def test_stores_the_provider_identity(self):
        self.mock_provider(self.google_routes())

        self.social_login(GOOGLE_URL)

        account = SocialAccount.objects.get(provider='google')
        self.assertEqual(account.provider_user_id, '1234567890')
        self.assertEqual(account.user.email, 'ryota@example.com')

    def test_new_user_has_no_usable_password_and_a_location(self):
        self.mock_provider(self.google_routes())

        self.social_login(GOOGLE_URL)

        user = User.objects.get(email='ryota@example.com')
        self.assertFalse(user.has_usable_password())
        self.assertEqual(UserLocation.objects.get(user=user).timezone, 'UTC')

    def test_username_comes_from_the_email_local_part(self):
        self.mock_provider(self.google_routes())

        response = self.social_login(GOOGLE_URL)

        self.assertEqual(response.data['username'], 'ryota')

    def test_username_is_deduplicated(self):
        self.create_user(username='ryota', email='taken@example.com')
        self.mock_provider(self.google_routes())

        response = self.social_login(GOOGLE_URL)

        self.assertEqual(response.data['username'], 'ryota2')

    def test_second_login_reuses_the_same_user(self):
        self.mock_provider(self.google_routes())

        first = self.social_login(GOOGLE_URL)
        second = self.social_login(GOOGLE_URL)

        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SocialAccount.objects.count(), 1)

    def test_links_to_an_existing_account_with_the_same_email(self):
        user = self.create_user(username='ryota', email='ryota@example.com')
        self.mock_provider(self.google_routes())

        response = self.social_login(GOOGLE_URL)

        self.assertEqual(response.data['id'], user.id)
        self.assertEqual(User.objects.count(), 1)
        self.assertTrue(user.social_accounts.filter(provider='google').exists())

    def test_password_login_still_works_after_linking(self):
        self.create_user(username='ryota', email='ryota@example.com')
        self.mock_provider(self.google_routes())
        self.social_login(GOOGLE_URL)

        response = self.login(identifier='ryota', password=VALID_PASSWORD)

        self.assertEqual(response.status_code, 200)

    def test_no_token_in_response_body(self):
        self.mock_provider(self.google_routes())

        response = self.social_login(GOOGLE_URL)
        body = response.content.decode()

        self.assertNotIn('google-access-token', body)
        self.assertNotIn(self.cookie(response, ACCESS_COOKIE).value, body)


class GoogleLoginFailureTests(SocialLoginTestCase):
    def assertRejected(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(ACCESS_COOKIE, response.cookies)
        self.assertNotIn(REFRESH_COOKIE, response.cookies)
        self.assertFalse(User.objects.exists())

    def test_missing_code(self):
        response = self.client.post(GOOGLE_URL, {}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('code', response.data)

    def test_invalid_code(self):
        self.mock_provider(
            self.google_routes(**{GOOGLE_TOKEN_URL: {'error': 'invalid_grant'}})
        )

        self.assertRejected(self.social_login(GOOGLE_URL))

    def test_rejected_token_exchange(self):
        self.mock_provider(
            self.google_routes(**{GOOGLE_TOKEN_URL: FakeResponse({'error': 'bad'}, 401)})
        )

        self.assertRejected(self.social_login(GOOGLE_URL))

    def test_unverified_email(self):
        self.mock_provider(
            self.google_routes(
                **{
                    GOOGLE_USERINFO_URL: {
                        'sub': '1234567890',
                        'email': 'ryota@example.com',
                        'email_verified': False,
                    }
                }
            )
        )

        response = self.social_login(GOOGLE_URL)

        self.assertRejected(response)
        self.assertEqual(
            response.data['detail'], 'Your Google account has no verified email address.'
        )

    def test_provider_unreachable(self):
        self.mock_provider(
            self.google_routes(**{GOOGLE_TOKEN_URL: requests.ConnectionError('boom')})
        )

        self.assertRejected(self.social_login(GOOGLE_URL))

    def test_unreadable_response(self):
        self.mock_provider(
            self.google_routes(**{GOOGLE_TOKEN_URL: FakeResponse(None)})
        )

        self.assertRejected(self.social_login(GOOGLE_URL))

    @override_settings(GOOGLE_OAUTH_CLIENT_SECRET='')
    def test_provider_not_configured(self):
        self.mock_provider({})

        response = self.social_login(GOOGLE_URL)

        self.assertRejected(response)
        self.assertEqual(response.data['detail'], 'This login provider is not configured.')

    def test_inactive_user_is_rejected(self):
        user = self.create_user(username='ryota', email='ryota@example.com')
        user.is_active = False
        user.save(update_fields=['is_active'])
        self.mock_provider(self.google_routes())

        response = self.social_login(GOOGLE_URL)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'This account is not active.')
        self.assertNotIn(ACCESS_COOKIE, response.cookies)


class GithubLoginTests(SocialLoginTestCase):
    def test_uses_the_primary_verified_email(self):
        self.mock_provider(self.github_routes())

        response = self.social_login(GITHUB_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], 'ryota@example.com')
        self.assertEqual(response.data['username'], 'ryota')
        self.assertCookieSet(response, ACCESS_COOKIE)

    def test_falls_back_to_any_verified_email(self):
        self.mock_provider(
            self.github_routes(
                **{
                    GITHUB_EMAILS_URL: [
                        {'email': 'unverified@example.com', 'primary': True, 'verified': False},
                        {'email': 'backup@example.com', 'primary': False, 'verified': True},
                    ]
                }
            )
        )

        response = self.social_login(GITHUB_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], 'backup@example.com')

    def test_stores_the_provider_identity(self):
        self.mock_provider(self.github_routes())

        self.social_login(GITHUB_URL)

        account = SocialAccount.objects.get(provider='github')
        self.assertEqual(account.provider_user_id, '42')

    def test_google_and_github_accounts_share_one_user(self):
        self.mock_provider(self.github_routes())
        github = self.social_login(GITHUB_URL)

        self.mock_provider(self.google_routes())
        google = self.social_login(GOOGLE_URL)

        self.assertEqual(github.data['id'], google.data['id'])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SocialAccount.objects.count(), 2)

    def test_no_verified_email(self):
        self.mock_provider(
            self.github_routes(
                **{
                    GITHUB_EMAILS_URL: [
                        {'email': 'ryota@example.com', 'primary': True, 'verified': False}
                    ]
                }
            )
        )

        response = self.social_login(GITHUB_URL)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['detail'], 'Your GitHub account has no verified email address.'
        )
        self.assertFalse(User.objects.exists())

    def test_invalid_code(self):
        self.mock_provider(
            self.github_routes(**{GITHUB_TOKEN_URL: {'error': 'bad_verification_code'}})
        )

        response = self.social_login(GITHUB_URL)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['detail'], 'The authorization code is invalid or expired.'
        )
        self.assertFalse(User.objects.exists())

    def test_username_falls_back_when_login_is_missing(self):
        self.mock_provider(self.github_routes(**{GITHUB_USER_URL: {'id': 42}}))

        response = self.social_login(GITHUB_URL)

        self.assertEqual(response.data['username'], 'user')
