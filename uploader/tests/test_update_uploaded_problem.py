import uuid

from problems.models import Problem, ProblemFile, UpdateProblem
from users.models import User

from .base import PASSWORD, UploaderTestCase


class UpdateUploadedProblemViewTests(UploaderTestCase):
    def setUp(self):
        super().setUp()
        self.problem = Problem.objects.create(
            title='Fix the cache', description='A broken cache layer',
            difficulty='medium', status='pending', created_by=self.user,
            field='backend', language='python', framework='django',
        )
        self.problem_file = ProblemFile.objects.create(
            problem=self.problem, directory='app/views.py', content='x = 1'
        )

    def other_users_file(self):
        other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        theirs = Problem.objects.create(
            title='Theirs', description='x', difficulty='easy',
            status='pending', created_by=other,
            field='backend', language='python', framework='django',
        )
        return ProblemFile.objects.create(problem=theirs, directory='app/models.py', content='y = 2')

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(
            self.update_url(self.problem_file.id), {'new_content': 'x = 2'}, format='json'
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(UpdateProblem.objects.count(), 0)

    def test_records_an_update_for_your_own_file(self):
        response = self.client.post(
            self.update_url(self.problem_file.id), {'new_content': 'x = 2'}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, {'message': 'Updates saved'})
        update = UpdateProblem.objects.get()
        self.assertEqual(update.problem, self.problem)
        self.assertEqual(update.problem_file, self.problem_file)
        self.assertEqual(update.new_content, 'x = 2')

    def test_original_file_is_not_changed_until_the_update_is_reviewed(self):
        self.client.post(
            self.update_url(self.problem_file.id), {'new_content': 'x = 2'}, format='json'
        )

        self.problem_file.refresh_from_db()
        self.assertEqual(self.problem_file.content, 'x = 1')

    def test_cannot_update_someone_elses_file(self):
        theirs = self.other_users_file()

        response = self.client.post(
            self.update_url(theirs.id), {'new_content': 'import os'}, format='json'
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(UpdateProblem.objects.count(), 0)

    def test_body_cannot_redirect_the_update_to_another_file(self):
        theirs = self.other_users_file()

        self.client.post(
            self.update_url(self.problem_file.id),
            {'new_content': 'x = 2', 'problem_file': theirs.id, 'problem': str(theirs.problem.id)},
            format='json',
        )

        update = UpdateProblem.objects.get()
        self.assertEqual(update.problem_file, self.problem_file)
        self.assertEqual(update.problem, self.problem)

    def test_unknown_file_is_404(self):
        response = self.client.post(
            self.update_url(uuid.uuid4()), {'new_content': 'x = 2'}, format='json'
        )

        self.assertEqual(response.status_code, 404)

    def test_missing_new_content_is_rejected(self):
        response = self.client.post(self.update_url(self.problem_file.id), {}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UpdateProblem.objects.count(), 0)
