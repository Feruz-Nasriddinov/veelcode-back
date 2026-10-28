from problems.models import Problem, ProblemFile, UpdateProblem
from users.models import User

from .base import PASSWORD, UploaderTestCase

HISTORY_URL = '/api/uploader/history/'


class UpdatesHistoryViewTests(UploaderTestCase):
    def make_update(self, author, title):
        problem = Problem.objects.create(
            title=f'{title} problem', description='x', difficulty='easy',
            status='pending', created_by=author,
            field='backend', language='python', framework='django',
        )
        problem_file = ProblemFile.objects.create(problem=problem, directory='app/views.py', content='x = 1')
        return UpdateProblem.objects.create(
            title=title, problem=problem, problem_file=problem_file, new_content='x = 2'
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, 401)

    def test_lists_only_updates_to_your_own_problems(self):
        mine = self.make_update(self.user, 'Mine')
        other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        self.make_update(other, 'Theirs')

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], mine.id)
        self.assertEqual(response.data[0]['title'], 'Mine')
        self.assertEqual(response.data[0]['status'], 'pending')
        self.assertEqual(response.data[0]['problem']['id'], str(mine.problem.id))
        self.assertEqual(response.data[0]['problem_file']['id'], str(mine.problem_file.id))

    def test_empty_when_you_have_no_updates(self):
        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
