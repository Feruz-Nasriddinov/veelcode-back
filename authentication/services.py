from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import UserLocation

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

    refresh = RefreshToken(raw_refresh)

    user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
    user = User.objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first()
    if user is None or not api_settings.USER_AUTHENTICATION_RULE(user):
        raise TokenError('No active account found for the given token.')

    if api_settings.BLACKLIST_AFTER_ROTATION:
        refresh.blacklist()

    refresh.set_jti()
    refresh.set_exp()
    refresh.set_iat()
    refresh.outstand()

    return refresh.access_token, refresh, user


def blacklist_refresh_token(raw_refresh):
    if not raw_refresh:
        return False
    try:
        RefreshToken(raw_refresh).blacklist()
    except TokenError:
        return False
    return True
