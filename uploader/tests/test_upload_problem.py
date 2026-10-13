import uuid

from problems.models import Problem

from .base import UPLOAD_URL, UploaderTestCase


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
        self.assertEqual(problem.source, 'https://github.com/acme/cache-service')

    def test_missing_source_is_rejected(self):
        payload = self.payload()
        del payload['source']

        response = self.client.post(UPLOAD_URL, payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('source', response.data)
        self.assertEqual(Problem.objects.count(), 0)

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
