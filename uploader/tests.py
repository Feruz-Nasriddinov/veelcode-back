import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import include, path
from rest_framework.test import APIClient

from problems.models import Problem, ProblemFile
from uploader.views import UploadProblemDetailView, UploadProblemView
from users.models import User

PASSWORD = 'Sup3rSecret!pass'

urlpatterns = [
    path('api/auth/', include('authentication.urls')),
    path('api/uploader/problem/', UploadProblemView.as_view()),
    path('api/uploader/problem/<uuid:problem_id>/content/', UploadProblemDetailView.as_view()),
]

UPLOAD_URL = '/api/uploader/problem/'


@override_settings(ROOT_URLCONF='uploader.tests')
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


class UploadProblemViewTests(UploaderTestCase):
    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(UPLOAD_URL, self.payload(), format='json')

        self.assertEqual(response.status_code, 401)

    def test_creates_a_pending_problem_owned_by_the_uploader(self):
        response = self.client.post(UPLOAD_URL, self.payload(), format='json')

        self.assertEqual(response.status_code, 201)
        problem = Problem.objects.get()
        self.assertEqual(problem.status, 'pending')
        self.assertEqual(problem.created_by, self.user)
        self.assertEqual(problem.title, 'Fix the cache')

    def test_response_does_not_leak_the_problem_id(self):
        response = self.client.post(UPLOAD_URL, self.payload(), format='json')

        self.assertEqual(response.data, {'message': 'Uploaded Problem will be checked'})

    def test_missing_fields_are_rejected(self):
        response = self.client.post(UPLOAD_URL, {'title': 'Only a title'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Problem.objects.count(), 0)

    def test_invalid_difficulty_is_rejected(self):
        response = self.client.post(UPLOAD_URL, self.payload(difficulty='impossible'), format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Problem.objects.count(), 0)

    def test_uploader_cannot_self_accept_a_problem(self):
        self.client.post(UPLOAD_URL, self.payload(status='accepted'), format='json')

        self.assertEqual(Problem.objects.get().status, 'pending')

    def test_uploader_cannot_choose_the_problem_id(self):
        chosen = uuid.uuid4()

        self.client.post(UPLOAD_URL, self.payload(id=str(chosen)), format='json')

        self.assertNotEqual(Problem.objects.get().id, chosen)

    def test_uploader_cannot_set_an_unbounded_time_limit(self):
        self.client.post(UPLOAD_URL, self.payload(time_required=86400), format='json')

        self.assertNotEqual(Problem.objects.get().time_required, 86400)


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


class UploaderRoutingTests(TestCase):
    def test_uploader_urlconf_uses_the_name_django_expects(self):
        import uploader.urls

        self.assertTrue(
            hasattr(uploader.urls, 'urlpatterns'),
            'uploader/urls.py defines url_patterns; include() only reads urlpatterns',
        )

    def test_upload_endpoints_are_reachable_in_the_real_urlconf(self):
        from django.urls import Resolver404, resolve

        try:
            resolve('/api/uploader/problem/')
        except Resolver404:
            self.fail('uploader views are not wired into config/urls.py')
