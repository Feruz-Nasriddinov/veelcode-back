from django.core.cache import cache
from django.test import TestCase
from config.testing import SecureAPIClient

from users.models import User

PASSWORD = 'Sup3rSecret!pass'

UPLOAD_URL = '/api/uploader/problem/'


class UploaderTestCase(TestCase):
    client_class = SecureAPIClient

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
            'source': 'https://github.com/acme/cache-service',
        }
        data.update(overrides)
        return data

    def files_url(self, problem_id):
        return f'/api/uploader/problem/{problem_id}/content/'

    def update_url(self, problem_file_id):
        return f'/api/uploader/content/{problem_file_id}/update/'
