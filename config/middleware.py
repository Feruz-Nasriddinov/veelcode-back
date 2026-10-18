from django.conf import settings
from django.http import HttpResponse


class RequestSizeLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            length = int(request.META.get('CONTENT_LENGTH') or 0)
        except ValueError:
            length = 0
        if length > settings.REQUEST_MAX_BYTES:
            return HttpResponse('Request body too large.', status=413)
        return self.get_response(request)
