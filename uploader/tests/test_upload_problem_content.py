import uuid
from unittest.mock import patch

from django.db import IntegrityError, transaction
from rest_framework.throttling import ScopedRateThrottle

from problems.models import Problem, ProblemFile
from users.models import User

from .base import PASSWORD, UPLOAD_URL, UploaderTestCase


class UploadProblemDetailViewTests(UploaderTestCase):
    def setUp(self):
        super().setUp()
        self.problem = Problem.objects.create(
            title='Fix the cache', description='A broken cache layer',
            difficulty='medium', status='pending', created_by=self.user,
            field='backend', language='python', framework='django',
        )

    def upload(self, files, problem=None):
        return self.client.post(self.files_url((problem or self.problem).id), files, format='json')

    def stored(self):
        return {f.directory: (f.content, f.is_hidden) for f in self.problem.files.all()}

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.upload({'app/views.py': {'content': 'x = 1'}})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_adds_several_files_in_one_request(self):
        response = self.upload({
            'app/views.py': {'content': 'x = 1'},
            'tests/test_hidden.py': {'content': 'assert True', 'is_hidden': True},
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.stored(), {
            'app/views.py': ('x = 1', False),
            'tests/test_hidden.py': ('assert True', True),
        })
        ids = {f.directory: str(f.id) for f in self.problem.files.all()}
        self.assertEqual(response.data, [
            {'id': ids['app/views.py'], 'directory': 'app/views.py', 'is_hidden': False},
            {'id': ids['tests/test_hidden.py'], 'directory': 'tests/test_hidden.py', 'is_hidden': True},
        ])

    def test_content_is_stored_exactly(self):
        response = self.upload({
            'app/__init__.py': {'content': ''},
            'app/views.py': {'content': '  x = 1\n\n'},
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.stored(), {
            'app/__init__.py': ('', False),
            'app/views.py': ('  x = 1\n\n', False),
        })

    def test_paths_are_normalized(self):
        self.upload({'app//./views.py': {'content': 'x = 1'}})

        self.assertEqual(self.problem.files.get().directory, 'app/views.py')

    def test_one_invalid_file_stores_nothing(self):
        response = self.upload({
            'app/views.py': {'content': 'x = 1'},
            '../escape.py': {'content': 'x = 1'},
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('../escape.py', response.data)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_invalid_is_hidden_is_rejected(self):
        response = self.upload({'app/views.py': {'content': 'x = 1', 'is_hidden': 'maybe'}})

        self.assertEqual(response.status_code, 400)
        self.assertIn('is_hidden', response.data['app/views.py'])
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_missing_content_is_rejected(self):
        response = self.upload({'app/views.py': {'is_hidden': True}})

        self.assertEqual(response.status_code, 400)
        self.assertIn('content', response.data['app/views.py'])
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_each_file_must_be_an_object(self):
        response = self.upload({'app/views.py': 'x = 1'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_body_must_be_a_non_empty_object(self):
        for body in ({}, [], ['app/views.py']):
            with self.subTest(body=body):
                self.assertEqual(self.upload(body).status_code, 400)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_same_path_twice_in_one_request_is_rejected(self):
        response = self.upload({
            'app/views.py': {'content': 'x = 1'},
            'app//views.py': {'content': 'x = 2'},
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_file_and_folder_with_the_same_path_are_rejected(self):
        response = self.upload({
            'app': {'content': 'x = 1'},
            'app/views.py': {'content': 'x = 1'},
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {'app', 'app/views.py'})
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_new_file_cannot_go_under_a_stored_file(self):
        ProblemFile.objects.create(problem=self.problem, directory='app', content='x = 1')

        response = self.upload({'app/views.py': {'content': 'x = 1'}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {'app/views.py'})
        self.assertEqual(self.problem.files.count(), 1)

    def test_new_file_cannot_take_a_stored_folders_path(self):
        ProblemFile.objects.create(problem=self.problem, directory='app/views.py', content='x = 1')

        response = self.upload({'app': {'content': 'x = 1'}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {'app'})
        self.assertEqual(self.problem.files.count(), 1)

    def test_stored_path_cannot_be_uploaded_again(self):
        ProblemFile.objects.create(problem=self.problem, directory='app/views.py', content='x = 1')

        response = self.upload({'app/views.py': {'content': 'import os'}})

        self.assertEqual(response.status_code, 400)
        self.assertIn('app/views.py', response.data)
        self.assertEqual(self.stored(), {'app/views.py': ('x = 1', False)})

    def test_database_rejects_duplicate_paths(self):
        ProblemFile.objects.create(problem=self.problem, directory='app/views.py', content='x = 1')

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProblemFile.objects.create(problem=self.problem, directory='app/views.py', content='x = 2')

    def test_cannot_add_files_to_someone_elses_problem(self):
        other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )
        theirs = Problem.objects.create(
            title='Theirs', description='x', difficulty='easy',
            status='pending', created_by=other,
            field='backend', language='python', framework='django',
        )

        response = self.upload({'app/views.py': {'content': 'x = 1'}}, problem=theirs)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_unknown_problem_is_404(self):
        response = self.client.post(
            self.files_url(uuid.uuid4()), {'app/views.py': {'content': 'x = 1'}}, format='json'
        )

        self.assertEqual(response.status_code, 404)

    def test_cannot_change_files_after_the_problem_is_accepted(self):
        self.problem.status = 'accepted'
        self.problem.save(update_fields=['status'])

        response = self.upload({'app/views.py': {'content': 'import os'}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProblemFile.objects.count(), 0)

    def test_cannot_change_files_after_the_problem_is_rejected(self):
        self.problem.status = 'rejected'
        self.problem.save(update_fields=['status'])

        response = self.upload({'app/views.py': {'content': 'x = 1'}})

        self.assertEqual(response.status_code, 400)

    def test_does_not_share_a_throttle_with_problem_creation(self):
        for _ in range(3):
            self.assertEqual(self.client.post(UPLOAD_URL, self.payload(), format='json').status_code, 201)
        self.assertEqual(self.client.post(UPLOAD_URL, self.payload(), format='json').status_code, 429)

        response = self.upload({'app/views.py': {'content': 'x = 1'}})

        self.assertEqual(response.status_code, 201)


class UploadProblemFileLimitTests(UploaderTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'upload-files': '1000/min'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.problem = Problem.objects.create(
            title='Fix the cache', description='A broken cache layer',
            difficulty='medium', status='pending', created_by=self.user,
            field='backend', language='python', framework='django',
        )

    def upload(self, files):
        return self.client.post(self.files_url(self.problem.id), files, format='json')

    def store(self, count, content='x'):
        ProblemFile.objects.bulk_create(
            ProblemFile(problem=self.problem, directory=f'f{i}.py', content=content) for i in range(count)
        )

    def test_path_traversal_in_directory_is_rejected(self):
        for directory in ('../escape.py', '/etc/passwd', 'a\\b.py', 'a/\x00b.py', '.'):
            with self.subTest(directory=directory):
                self.assertEqual(self.upload({directory: {'content': 'x = 1'}}).status_code, 400)
        self.assertEqual(self.problem.files.count(), 0)

    def test_oversized_file_is_rejected(self):
        self.assertEqual(self.upload({'a.py': {'content': 'x' * (256 * 1024 + 1)}}).status_code, 400)
        self.assertEqual(self.upload({'a.py': {'content': 'x' * (256 * 1024)}}).status_code, 201)

    def test_too_many_files_in_one_request_are_rejected(self):
        files = {f'f{i}.py': {'content': 'x'} for i in range(201)}

        self.assertEqual(self.upload(files).status_code, 400)
        self.assertEqual(self.problem.files.count(), 0)

    def test_file_count_includes_stored_files(self):
        self.store(199)

        self.assertEqual(self.upload({'a.py': {'content': 'x'}, 'b.py': {'content': 'x'}}).status_code, 400)
        self.assertEqual(self.upload({'a.py': {'content': 'x'}}).status_code, 201)

    def test_total_size_includes_stored_files(self):
        self.store(4, content='x' * (256 * 1024))

        self.assertEqual(self.upload({'a.py': {'content': 'x'}}).status_code, 400)

    def test_total_size_counts_every_file_in_the_request(self):
        big = {'content': 'x' * (256 * 1024)}

        self.assertEqual(self.upload({f'f{i}.py': big for i in range(5)}).status_code, 400)
        self.assertEqual(self.upload({f'f{i}.py': big for i in range(4)}).status_code, 201)

    def test_oversized_update_is_rejected(self):
        problem_file = ProblemFile.objects.create(problem=self.problem, directory='a.py', content='x')

        response = self.client.post(
            self.update_url(problem_file.id), {'new_content': 'x' * (256 * 1024 + 1)}, format='json'
        )

        self.assertEqual(response.status_code, 400)
