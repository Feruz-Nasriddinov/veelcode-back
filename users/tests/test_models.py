from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from users.models import User, Submission, UserLocation

from .base import PASSWORD, UsersTestCase


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


class SubmissionModelTests(UsersTestCase):
    def test_defaults(self):
        submission = Submission.objects.create(user=self.user, problem=self.problem)

        self.assertEqual(submission.score, 0)
        self.assertEqual(submission.status, 'pending')
        self.assertIsNone(submission.error_message)

    def test_str(self):
        submission = self.make_submission(score=80)

        self.assertEqual(str(submission), 'ryota-80')

    def test_related_names(self):
        submission = self.make_submission()

        self.assertIn(submission, self.user.submissions.all())
        self.assertIn(submission, self.problem.submissions.all())

    def test_deleting_the_user_deletes_their_submissions(self):
        self.make_submission()

        self.user.submissions.all().delete()

        self.assertEqual(Submission.objects.count(), 0)

    def test_deleting_the_problem_cascades_to_submissions(self):
        self.make_submission()

        self.problem.delete()

        self.assertEqual(Submission.objects.count(), 0)


class UserLocationModelTests(UsersTestCase):
    def test_timezone_defaults_to_utc(self):
        location = UserLocation.objects.create(user=self.user)

        self.assertEqual(location.timezone, 'UTC')

    def test_str(self):
        location = UserLocation.objects.create(user=self.user, timezone='Asia/Tokyo')

        self.assertEqual(str(location), 'ryota - Asia/Tokyo')

    def test_related_name(self):
        location = UserLocation.objects.create(user=self.user)

        self.assertEqual(self.user.location, location)
