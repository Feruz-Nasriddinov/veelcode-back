import uuid

from problems.models import Problem, ProblemFile

from .base import ProblemsTestCase


class ProblemModelTests(ProblemsTestCase):
    def test_str(self):
        problem = self.make_problem()

        self.assertEqual(str(problem), 'Fix the cache-medium')

    def test_id_is_a_uuid_by_default(self):
        problem = self.make_problem()

        self.assertIsInstance(problem.id, uuid.UUID)

    def test_time_required_defaults_to_0(self):
        problem = self.make_problem()

        self.assertEqual(problem.time_required, 0)

    def test_creator_is_protected_from_deletion(self):
        from django.db.models import ProtectedError

        self.make_problem()

        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_description_has_a_max_length(self):
        field = Problem._meta.get_field('description')

        self.assertEqual(field.max_length, 500)

    def test_field_language_and_framework_are_stored(self):
        problem = self.make_problem(
            field='frontend', language='typescript', framework='react'
        )
        problem.refresh_from_db()

        self.assertEqual(problem.field, 'frontend')
        self.assertEqual(problem.language, 'typescript')
        self.assertEqual(problem.framework, 'react')

    def test_a_value_outside_the_choices_is_rejected(self):
        from django.core.exceptions import ValidationError

        problem = self.make_problem(field='mobile')

        with self.assertRaises(ValidationError):
            problem.full_clean()

    def test_problem_file_str_and_cascade(self):
        problem = self.make_problem()
        pf = ProblemFile.objects.create(problem=problem, directory='app/views.py', content='x = 1')

        self.assertEqual(str(pf), 'Fix the cache-app/views.py')

        problem.delete()
        self.assertEqual(ProblemFile.objects.count(), 0)
