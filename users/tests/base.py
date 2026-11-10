from datetime import datetime

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from config.testing import SecureAPIClient

from problems.models import Problem
from users.models import User, Submission

PASSWORD = 'Sup3rSecret!pass'


class UsersTestCase(TestCase):
    client_class = SecureAPIClient

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(
            username='ryota', email='ryota@example.com', password=PASSWORD
        )
        self.other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        self.problem = Problem.objects.create(
            title='Fix the cache', description='A broken cache layer',
            difficulty='medium', status='accepted', created_by=self.user,
            field='backend', language='python', framework='django',
        )
        self.client.force_authenticate(self.user)

    def make_submission(self, user=None, created_at=None, **overrides):
        data = {'user': user or self.user, 'problem': self.problem, 'status': 'done'}
        data.update(overrides)
        submission = Submission.objects.create(**data)
        if created_at is not None:
            Submission.objects.filter(pk=submission.pk).update(created_at=created_at)
        return submission

    def aware(self, *args):
        return timezone.make_aware(datetime(*args))
