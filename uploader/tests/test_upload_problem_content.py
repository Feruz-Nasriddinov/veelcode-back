import uuid

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
        self.assertEqual(self.problem.files.get().directory, 'app/views.py')
        self.assertFalse(self.problem.files.get().is_hidden)

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
