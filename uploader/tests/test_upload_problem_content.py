import uuid
from unittest.mock import patch

from rest_framework.throttling import ScopedRateThrottle

from problems.models import Problem, ProblemFile
from users.models import User

from .base import PASSWORD, UploaderTestCase


class UploadProblemDetailViewTests(UploaderTestCase):
    def setUp(self):
        super().setUp()
        self.problem = Problem.objects.create(
            title='Fix the cache', description='A broken cache layer',
            difficulty='medium', status='pending', created_by=self.user,
            field='backend', language='python', framework='django',
        )

    def file_payload(self, **overrides):
        data = {'directory': 'app/views.py', 'content': 'x = 1'}
        data.update(overrides)
        return data

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(
            self.files_url(self.problem.id), self.file_payload(), format='json'
        )

        self.assertEqual(response.status_code, 401)

    def test_adds_a_file_to_your_own_problem(self):
        response = self.client.post(
            self.files_url(self.problem.id), self.file_payload(), format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.problem.files.count(), 1)
        problem_file = self.problem.files.get()
        self.assertEqual(problem_file.directory, 'app/views.py')
        self.assertFalse(problem_file.is_hidden)
        self.assertEqual(response.data, {
            'id': str(problem_file.id), 'directory': 'app/views.py', 'content': 'x = 1', 'is_hidden': False,
        })

    def test_adds_a_hidden_test_file(self):
        response = self.client.post(
            self.files_url(self.problem.id),
            self.file_payload(directory='tests/test_hidden.py', is_hidden=True),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.problem.files.get().is_hidden)

    def test_invalid_is_hidden_is_rejected(self):
        response = self.client.post(
            self.files_url(self.problem.id), self.file_payload(is_hidden='maybe'), format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_cannot_add_files_to_someone_elses_problem(self):
        other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        theirs = Problem.objects.create(
            title='Theirs', description='x', difficulty='easy',
            status='pending', created_by=other,
            field='backend', language='python', framework='django',
        )

        response = self.client.post(
            self.files_url(theirs.id), self.file_payload(), format='json'
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_unknown_problem_is_404(self):
        response = self.client.post(
            self.files_url(uuid.uuid4()), self.file_payload(), format='json'
        )

        self.assertEqual(response.status_code, 404)

    def test_missing_fields_are_rejected(self):
        response = self.client.post(
            self.files_url(self.problem.id), {'directory': 'app/views.py'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_cannot_change_files_after_the_problem_is_accepted(self):
        self.problem.status = 'accepted'
        self.problem.save(update_fields=['status'])

        response = self.client.post(
            self.files_url(self.problem.id), self.file_payload(content='import os'), format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_cannot_change_files_after_the_problem_is_rejected(self):
        self.problem.status = 'rejected'
        self.problem.save(update_fields=['status'])

        response = self.client.post(
            self.files_url(self.problem.id), self.file_payload(), format='json'
        )

        self.assertEqual(response.status_code, 400)


class UploadProblemFileLimitTests(UploaderTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'upload-problem': '1000/min'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.problem = Problem.objects.create(
            title='Fix the cache', description='A broken cache layer',
            difficulty='medium', status='pending', created_by=self.user,
            field='backend', language='python', framework='django',
        )

    def upload(self, **overrides):
        data = {'directory': 'app/views.py', 'content': 'x = 1'}
        data.update(overrides)
        return self.client.post(self.files_url(self.problem.id), data, format='json')

    def test_path_traversal_in_directory_is_rejected(self):
        for directory in ('../escape.py', '/etc/passwd', 'a\\b.py', 'a/\x00b.py'):
            with self.subTest(directory=directory):
                self.assertEqual(self.upload(directory=directory).status_code, 400)
        self.assertEqual(self.problem.files.count(), 0)

    def test_oversized_file_is_rejected(self):
        self.assertEqual(self.upload(content='x' * (256 * 1024 + 1)).status_code, 400)
        self.assertEqual(self.upload(content='x' * (256 * 1024)).status_code, 201)

    def test_too_many_files_are_rejected(self):
        for i in range(200):
            ProblemFile.objects.create(problem=self.problem, directory=f'f{i}.py', content='x')

        self.assertEqual(self.upload(directory='one_more.py').status_code, 400)

    def test_total_size_is_capped(self):
        for i in range(4):
            ProblemFile.objects.create(problem=self.problem, directory=f'f{i}.py', content='x' * (256 * 1024))

        self.assertEqual(self.upload().status_code, 400)

    def test_oversized_update_is_rejected(self):
        problem_file = ProblemFile.objects.create(problem=self.problem, directory='a.py', content='x')

        response = self.client.post(
            self.update_url(problem_file.id), {'new_content': 'x' * (256 * 1024 + 1)}, format='json'
        )

        self.assertEqual(response.status_code, 400)
