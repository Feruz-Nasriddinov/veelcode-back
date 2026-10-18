from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.http import HttpResponse
from rest_framework.throttling import BaseThrottle


def throttled_admin_login(request):
    if request.method == 'POST':
        key = f'admin-login:{BaseThrottle().get_ident(request)}'
        cache.add(key, 0, 60)
        if cache.incr(key) > settings.ADMIN_LOGIN_MAX_ATTEMPTS_PER_MINUTE:
            return HttpResponse('Too many login attempts.', status=429)
    return admin.site.login(request)
