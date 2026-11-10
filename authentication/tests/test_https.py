from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .base import CSRF_URL, LOGIN_URL


@override_settings(SECURE_SSL_REDIRECT=True)
class HttpsRedirectTests(TestCase):
    client_class = APIClient

    def test_http_get_redirects_to_https(self):
        response = self.client.get(CSRF_URL)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], f'https://testserver{CSRF_URL}')

    def test_http_post_redirects_to_https(self):
        response = self.client.post(LOGIN_URL, {'identifier': 'a', 'password': 'b'}, format='json')

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], f'https://testserver{LOGIN_URL}')

    def test_https_request_is_served(self):
        self.assertEqual(self.client.get(CSRF_URL, secure=True).status_code, 204)

    def test_forwarded_proto_https_from_the_proxy_is_served(self):
        response = self.client.get(CSRF_URL, HTTP_X_FORWARDED_PROTO='https')

        self.assertEqual(response.status_code, 204)

    def test_forwarded_proto_http_from_the_proxy_redirects(self):
        response = self.client.get(CSRF_URL, HTTP_X_FORWARDED_PROTO='http')

        self.assertEqual(response.status_code, 301)


@override_settings(SECURE_SSL_REDIRECT=False)
class DebugHttpTests(TestCase):
    client_class = APIClient

    def test_http_is_served_when_redirect_is_off(self):
        self.assertEqual(self.client.get(CSRF_URL).status_code, 204)
