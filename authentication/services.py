import re
import time

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from users.models import SocialAccount, UserLocation

from .oauth import PROFILE_FETCHERS, OAuthError

User = get_user_model()


@transaction.atomic
def create_user(*, username, email, password, timezone='UTC'):
    user = User.objects.create_user(username=username, email=email, password=password)
    UserLocation.objects.create(user=user, timezone=timezone)
    return user


def find_user_by_identifier(identifier):
    identifier = (identifier or '').strip()
    if not identifier:
        return None
    field = 'email' if '@' in identifier else 'username'
    return User.objects.filter(**{f'{field}__iexact': identifier}).first()


def authenticate_user(*, identifier, password):
    user = find_user_by_identifier(identifier)
    if user is None:
        User().set_password(password)
        return None
    if not user.check_password(password):
        return None
    if not api_settings.USER_AUTHENTICATION_RULE(user):
        return None
    return user


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return refresh.access_token, refresh


def rotate_refresh_token(raw_refresh):
    if not raw_refresh:
        raise TokenError('No refresh token provided.')

    try:
        refresh = RefreshToken(raw_refresh)
    except TokenError:
        _revoke_family_if_reused(raw_refresh)
        raise

    user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
    user = User.objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first()
    if user is None or not api_settings.USER_AUTHENTICATION_RULE(user):
        raise TokenError('No active account found for the given token.')

    if api_settings.BLACKLIST_AFTER_ROTATION:
        _, newly_blacklisted = refresh.blacklist()
        if not newly_blacklisted:
            revoke_all_refresh_tokens(user)
            raise TokenError('Token is blacklisted')

    refresh.set_jti()
    refresh.set_exp()
    refresh.set_iat()
    refresh.outstand()

    return refresh.access_token, refresh, user


def revoke_all_refresh_tokens(user):
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)


def _revoke_family_if_reused(raw_refresh):
    try:
        token = RefreshToken(raw_refresh, verify=False)
        jti = token.payload[api_settings.JTI_CLAIM]
        token.verify_token_type()
        token.check_exp()
    except (TokenError, KeyError):
        return
    outstanding = OutstandingToken.objects.filter(jti=jti).select_related('user').first()
    if outstanding and outstanding.user and BlacklistedToken.objects.filter(token=outstanding).exists():
        revoke_all_refresh_tokens(outstanding.user)


def blacklist_refresh_token(raw_refresh):
    if not raw_refresh:
        return False
    try:
        RefreshToken(raw_refresh).blacklist()
    except TokenError:
        return False
    return True


def _revoked_key(jti):
    return f'revoked-access:{jti}'


def revoke_access_token(raw_access):
    if not raw_access:
        return
    try:
        token = AccessToken(raw_access)
    except TokenError:
        return
    ttl = int(token['exp'] - time.time())
    if ttl > 0:
        cache.set(_revoked_key(token[api_settings.JTI_CLAIM]), 1, ttl)


def is_access_token_revoked(validated_token):
    return cache.get(_revoked_key(validated_token[api_settings.JTI_CLAIM])) is not None


def unique_username(seed):
    base = re.sub(r'[^\w.+-]', '', (seed or '').strip(), flags=re.ASCII)[:140] or 'user'
    username = base
    suffix = 1
    while User.objects.filter(username__iexact=username).exists():
        suffix += 1
        username = f'{base}{suffix}'
    return username


@transaction.atomic
def link_social_account(*, provider, provider_user_id, email, username_seed):
    account = (
        SocialAccount.objects
        .select_related('user')
        .filter(provider=provider, provider_user_id=provider_user_id)
        .first()
    )
    if account is not None:
        return account.user

    email = User.objects.normalize_email(email.strip())
    user = User.objects.filter(email__iexact=email).first()
    if user is not None and user.has_usable_password():
        raise OAuthError('An account with this email already exists. Log in with your password.')
    if user is None:
        user = User.objects.create_user(
            username=unique_username(username_seed),
            email=email,
            password=None,
        )
        UserLocation.objects.create(user=user)

    SocialAccount.objects.create(
        user=user,
        provider=provider,
        provider_user_id=provider_user_id,
    )
    return user


def authenticate_social_user(*, provider, code):
    profile = PROFILE_FETCHERS[provider](code)
    user = link_social_account(**profile)
    if not api_settings.USER_AUTHENTICATION_RULE(user):
        raise OAuthError('This account is not active.')
    return user
