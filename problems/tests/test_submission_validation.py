from unittest.mock import patch

from users.models import Submission

from .base import ProblemsTestCase


class SubmissionValidationTests(ProblemsTestCase):
    def url(self, problem_id):
        return f'/api/problems/{problem_id}/submit/'

    def setUp(self):
        super().setUp()
        self.problem = self.make_problem()

    def submit(self, payload):
        with patch('problems.views.evaluate_tasks.apply_async') as delay:
            response = self.client.post(self.url(self.problem.id), payload, format='json')
        return response, delay

    def assertRejected(self, payload):
        response, delay = self.submit(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Submission.objects.count(), 0)
        delay.assert_not_called()
        return response

    def test_parent_directory_traversal_is_rejected(self):
        self.assertRejected({'../../etc/passwd': 'root'})

    def test_traversal_in_the_middle_of_a_path_is_rejected(self):
        self.assertRejected({'app/../../escape.py': 'x = 1'})

    def test_absolute_path_is_rejected(self):
        self.assertRejected({'/etc/passwd': 'root'})

    def test_backslash_separator_is_rejected(self):
        self.assertRejected({'app\\views.py': 'x = 1'})

    def test_null_byte_in_path_is_rejected(self):
        self.assertRejected({'app/\x00views.py': 'x = 1'})

    def test_overlong_path_is_rejected(self):
        self.assertRejected({'a' * 300: 'x = 1'})

    def test_empty_submission_is_rejected(self):
        self.assertRejected({})

    def test_non_object_payload_is_rejected(self):
        self.assertRejected(['main.py'])

    def test_non_string_content_is_rejected(self):
        self.assertRejected({'main.py': {'nested': 'object'}})

    def test_too_many_files_are_rejected(self):
        from django.conf import settings

        payload = {f'f{i}.py': 'x = 1' for i in range(settings.SUBMISSION_MAX_FILES + 1)}

        self.assertRejected(payload)

    def test_oversized_submission_is_rejected(self):
        from django.conf import settings

        self.assertRejected({'big.py': 'x' * (settings.SUBMISSION_MAX_TOTAL_BYTES + 1)})

    def test_nested_relative_paths_are_accepted(self):
        response, delay = self.submit({'app/core/views.py': 'x = 1', 'README.md': 'hi'})

        self.assertEqual(response.status_code, 202)
        delay.assert_called_once()

    def test_only_validated_files_reach_the_broker(self):
        response, delay = self.submit({'./app/views.py': 'x = 1'})

        self.assertEqual(response.status_code, 202)
        submission_id, files = delay.call_args.kwargs['args']
        self.assertEqual(files, {'app/views.py': 'x = 1'})
        self.assertEqual(submission_id, Submission.objects.get().id)
