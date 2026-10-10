import requests
from django.conf import settings

from users.models import SocialAccount

GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
GITHUB_USER_URL = 'https://api.github.com/user'
GITHUB_EMAILS_URL = 'https://api.github.com/user/emails'

REQUEST_TIMEOUT = 10


class OAuthError(Exception):
    pass


def _request(method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.RequestException:
        raise OAuthError('Could not reach the identity provider.')

    if response.status_code >= 400:
        raise OAuthError('The identity provider rejected the request.')

    try:
        return response.json()
    except ValueError:
        raise OAuthError('The identity provider returned an unreadable response.')


def _exchange_code(url, code, client_id, client_secret, redirect_uri, extra=None, headers=None):
    if not (client_id and client_secret and redirect_uri):
        raise OAuthError('This login provider is not configured.')

    data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
    }
    data.update(extra or {})

    token = _request('POST', url, data=data, headers=headers)
    access_token = token.get('access_token')
    if not access_token:
        raise OAuthError('The authorization code is invalid or expired.')
    return access_token


def fetch_google_profile(code):
    access_token = _exchange_code(
        GOOGLE_TOKEN_URL,
        code,
        settings.GOOGLE_OAUTH_CLIENT_ID,
        settings.GOOGLE_OAUTH_CLIENT_SECRET,
        settings.GOOGLE_OAUTH_REDIRECT_URI,
        extra={'grant_type': 'authorization_code'},
    )

    info = _request(
        'GET',
        GOOGLE_USERINFO_URL,
        headers={'Authorization': f'Bearer {access_token}'},
    )

    provider_user_id = info.get('sub')
    email = info.get('email')
    if not provider_user_id:
        raise OAuthError('Google did not return an account id.')
    if not email or not info.get('email_verified'):
        raise OAuthError('Your Google account has no verified email address.')

    return {
        'provider': SocialAccount.GOOGLE,
        'provider_user_id': str(provider_user_id),
        'email': email,
        'username_seed': email.split('@')[0],
    }


def fetch_github_profile(code):
    access_token = _exchange_code(
        GITHUB_TOKEN_URL,
        code,
        settings.GITHUB_OAUTH_CLIENT_ID,
        settings.GITHUB_OAUTH_CLIENT_SECRET,
        settings.GITHUB_OAUTH_REDIRECT_URI,
        headers={'Accept': 'application/json'},
    )

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/vnd.github+json',
    }
    user = _request('GET', GITHUB_USER_URL, headers=headers)

    provider_user_id = user.get('id')
    if not provider_user_id:
        raise OAuthError('GitHub did not return an account id.')

    return {
        'provider': SocialAccount.GITHUB,
        'provider_user_id': str(provider_user_id),
        'email': _github_verified_email(headers),
        'username_seed': user.get('login') or '',
    }


def _github_verified_email(headers):
    emails = _request('GET', GITHUB_EMAILS_URL, headers=headers)
    if not isinstance(emails, list):
        raise OAuthError('GitHub returned an unreadable email list.')

    verified = [entry for entry in emails if entry.get('verified') and entry.get('email')]
    for entry in verified:
        if entry.get('primary'):
            return entry['email']
    if verified:
        return verified[0]['email']

    raise OAuthError('Your GitHub account has no verified email address.')


PROFILE_FETCHERS = {
    SocialAccount.GOOGLE: fetch_google_profile,
    SocialAccount.GITHUB: fetch_github_profile,
}
