from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from users.models import User

PASSWORD = 'Sup3rSecret!pass'

UPLOAD_URL = '/api/uploader/problem/'


@override_settings(ROOT_URLCONF='uploader.tests.urls')
class UploaderTestCase(TestCase):
    client_class = APIClient

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(
            username='ryota', email='ryota@example.com', password=PASSWORD
        )
        self.client.force_authenticate(self.user)

    def payload(self, **overrides):
        data = {
            'title': 'Fix the cache',
            'description': 'A broken cache layer',
            'difficulty': 'medium',
            'field': 'backend',
            'language': 'python',
            'framework': 'django',
        }
        data.update(overrides)
        return data

    def files_url(self, problem_id):
        return f'/api/uploader/problem/{problem_id}/content/'

    def update_url(self, problem_file_id):
        return f'/api/uploader/content/{problem_file_id}/update/'
