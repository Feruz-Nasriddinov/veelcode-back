from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from problems.models import Problem
from users.models import User, UserDetail

PASSWORD = 'Sup3rSecret!pass'


class UserModelTests(TestCase):
    def test_create_user_hashes_the_password(self):
        user = User.objects.create_user(username='ryota', email='ryota@example.com', password=PASSWORD)

        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_create_superuser(self):
        user = User.objects.create_superuser(username='root', email='root@example.com', password=PASSWORD)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_username_field_and_required_fields(self):
        self.assertEqual(User.USERNAME_FIELD, 'username')
        self.assertIn('email', User.REQUIRED_FIELDS)

    def test_username_with_at_sign_is_invalid(self):
        user = User(username='ryota@home', email='ryota@example.com')

        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()

        self.assertIn('username', ctx.exception.error_dict)

    def test_username_allows_dot_dash_underscore_plus(self):
        user = User(username='ry.ota_1-x+y', email='ryota@example.com')
        user.set_password(PASSWORD)

        user.full_clean()

    def test_blank_email_is_invalid(self):
        user = User(username='ryota', email='')

        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()

        self.assertIn('email', ctx.exception.error_dict)

    def test_malformed_email_is_invalid(self):
        user = User(username='ryota', email='not-an-email')

        with self.assertRaises(ValidationError) as ctx:
            user.full_clean()

        self.assertIn('email', ctx.exception.error_dict)


class UserUniquenessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='ryota', email='ryota@example.com', password=PASSWORD
        )

    def test_exact_duplicate_username_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username='ryota', email='other@example.com', password=PASSWORD)

    def test_case_insensitive_duplicate_username_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username='RyOtA', email='other@example.com', password=PASSWORD)

    def test_exact_duplicate_email_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username='other', email='ryota@example.com', password=PASSWORD)

    def test_case_insensitive_duplicate_email_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username='other', email='RYOTA@EXAMPLE.COM', password=PASSWORD)

    def test_lookup_is_case_insensitive_both_ways(self):
        self.assertEqual(User.objects.get(username__iexact='RYOTA'), self.user)
        self.assertEqual(User.objects.get(email__iexact='Ryota@Example.com'), self.user)

    def test_constraints_are_present_on_the_model(self):
        names = {c.name for c in User._meta.constraints}

        self.assertEqual(names, {'user_username_lower_unique', 'user_email_lower_unique'})


class UserDetailModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='ryota', email='ryota@example.com', password=PASSWORD
        )
        self.problem = Problem.objects.create(
            title='Fix the cache', description='A broken cache layer',
            difficulty='medium', status='accepted', created_by=self.user,
            field='backend', language='python', framework='django',
        )

    def make_detail(self, **overrides):
        data = {'user': self.user, 'problem': self.problem, 'status': 'pending'}
        data.update(overrides)
        return UserDetail.objects.create(**data)

    def test_defaults(self):
        detail = self.make_detail()

        self.assertEqual(detail.score, 0)
        self.assertIsNone(detail.error_message)

    def test_str(self):
        detail = self.make_detail(score=80)

        self.assertEqual(str(detail), 'ryota-80')

    def test_related_names(self):
        detail = self.make_detail()

        self.assertIn(detail, self.user.details.all())
        self.assertIn(detail, self.problem.details.all())

    def test_deleting_the_user_deletes_their_submissions(self):
        self.make_detail()

        self.user.details.all().delete()

        self.assertEqual(UserDetail.objects.count(), 0)

    def test_deleting_the_problem_cascades_to_submissions(self):
        self.make_detail()

        self.problem.delete()

        self.assertEqual(UserDetail.objects.count(), 0)
