from django.conf import settings
from rest_framework_simplejwt.settings import api_settings


def _base_kwargs(path):
    return {
        'httponly': True,
        'secure': settings.AUTH_COOKIE_SECURE,
        'samesite': settings.AUTH_COOKIE_SAMESITE,
        'domain': settings.AUTH_COOKIE_DOMAIN,
        'path': path,
    }


def set_access_cookie(response, token):
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE_NAME,
        str(token),
        max_age=int(api_settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
        **_base_kwargs(settings.AUTH_ACCESS_COOKIE_PATH),
    )


def set_refresh_cookie(response, token):
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        str(token),
        max_age=int(api_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        **_base_kwargs(settings.AUTH_REFRESH_COOKIE_PATH),
    )


def set_auth_cookies(response, access_token, refresh_token):
    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)
    return response


def clear_auth_cookies(response):
    for name, path in (
        (settings.AUTH_ACCESS_COOKIE_NAME, settings.AUTH_ACCESS_COOKIE_PATH),
        (settings.AUTH_REFRESH_COOKIE_NAME, settings.AUTH_REFRESH_COOKIE_PATH),
    ):
        response.set_cookie(name, '', max_age=0, **_base_kwargs(path))
    return response
