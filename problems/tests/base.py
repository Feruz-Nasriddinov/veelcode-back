from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from problems.models import Problem, ProblemFile
from users.models import User

PASSWORD = 'Sup3rSecret!pass'


class ProblemsTestCase(TestCase):
    client_class = APIClient

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(
            username='ryota', email='ryota@example.com', password=PASSWORD
        )
        self.client.force_authenticate(self.user)

    def make_problem(self, **overrides):
        data = {
            'title': 'Fix the cache',
            'description': 'A broken cache layer',
            'difficulty': 'medium',
            'status': 'accepted',
            'field': 'backend',
            'language': 'python',
            'framework': 'django',
            'created_by': self.user,
        }
        data.update(overrides)
        return Problem.objects.create(**data)

    def make_problem_with_hidden_tests(self, hidden=None, **overrides):
        problem = self.make_problem(**overrides)
        hidden = hidden or {'test_hidden.py': 'def test_a():\n    assert 1\n'}
        for directory, content in hidden.items():
            ProblemFile.objects.create(
                problem=problem, directory=directory, content=content, is_hidden=True
            )
        return problem
