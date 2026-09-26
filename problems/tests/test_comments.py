import uuid

from django.conf import settings

from problems.models import Comment, Like
from problems.views import (
    CommentDeleteView,
    CommentPatchView,
    CommentView,
    LikeView,
    UnlikeView,
)
from users.models import User

from .base import PASSWORD, ProblemsTestCase


URLS = {
    CommentView: '/api/problems/{problem_id}/comments/',
    CommentPatchView: '/api/comments/{comment_id}/edit/',
    CommentDeleteView: '/api/comments/{comment_id}/delete/',
    LikeView: '/api/comments/{comment_id}/like/',
    UnlikeView: '/api/comments/{comment_id}/unlike/',
}


class CommentViewTestCase(ProblemsTestCase):
    def setUp(self):
        super().setUp()
        self.problem = self.make_problem()
        self.other = User.objects.create_user(
            username='other', email='other@example.com', password=PASSWORD
        )

    def call(self, view, method, data=None, user=None, **kwargs):
        self.client.force_authenticate(None if user is False else user or self.user)
        return getattr(self.client, method)(URLS[view].format(**kwargs), data, format='json')

    def make_comment(self, user=None, text='Nice problem'):
        return Comment.objects.create(user=user or self.user, problem=self.problem, text=text)


class CommentCreateViewTests(CommentViewTestCase):
    def test_requires_authentication(self):
        response = self.call(
            CommentView, 'post', {'text': 'hi'}, user=False, problem_id=self.problem.id
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Comment.objects.count(), 0)

    def test_creates_a_comment_for_the_user(self):
        response = self.call(CommentView, 'post', {'text': 'hi'}, problem_id=self.problem.id)

        self.assertEqual(response.status_code, 201)
        comment = Comment.objects.get()
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.problem, self.problem)
        self.assertEqual(comment.text, 'hi')

    def test_user_in_the_body_is_ignored(self):
        self.call(
            CommentView, 'post', {'text': 'hi', 'user': self.other.id}, problem_id=self.problem.id
        )

        self.assertEqual(Comment.objects.get().user, self.user)

    def test_missing_text_is_rejected(self):
        response = self.call(CommentView, 'post', {}, problem_id=self.problem.id)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Comment.objects.count(), 0)

    def test_overlong_text_is_rejected(self):
        response = self.call(
            CommentView, 'post', {'text': 'x' * 1001}, problem_id=self.problem.id
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Comment.objects.count(), 0)

    def test_unknown_problem_is_404(self):
        response = self.call(CommentView, 'post', {'text': 'hi'}, problem_id=uuid.uuid4())

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Comment.objects.count(), 0)


class CommentPatchViewTests(CommentViewTestCase):
    def test_requires_authentication(self):
        comment = self.make_comment()

        response = self.call(
            CommentPatchView, 'patch', {'text': 'edited'}, user=False, comment_id=comment.id
        )

        self.assertEqual(response.status_code, 401)

    def test_edits_the_users_comment(self):
        comment = self.make_comment()

        response = self.call(CommentPatchView, 'patch', {'text': 'edited'}, comment_id=comment.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'id': comment.id, 'text': 'edited'})
        comment.refresh_from_db()
        self.assertEqual(comment.text, 'edited')

    def test_another_users_comment_is_not_editable(self):
        comment = self.make_comment(user=self.other)

        response = self.call(CommentPatchView, 'patch', {'text': 'edited'}, comment_id=comment.id)

        self.assertEqual(response.status_code, 404)
        comment.refresh_from_db()
        self.assertEqual(comment.text, 'Nice problem')

    def test_unknown_comment_is_404(self):
        response = self.call(CommentPatchView, 'patch', {'text': 'edited'}, comment_id=999)

        self.assertEqual(response.status_code, 404)

    def test_overlong_text_is_rejected(self):
        comment = self.make_comment()

        response = self.call(CommentPatchView, 'patch', {'text': 'x' * 1001}, comment_id=comment.id)

        self.assertEqual(response.status_code, 400)
        comment.refresh_from_db()
        self.assertEqual(comment.text, 'Nice problem')


class CommentDeleteViewTests(CommentViewTestCase):
    def test_requires_authentication(self):
        comment = self.make_comment()

        response = self.call(CommentDeleteView, 'delete', user=False, comment_id=comment.id)

        self.assertEqual(response.status_code, 401)
        self.assertTrue(Comment.objects.filter(id=comment.id).exists())

    def test_deletes_the_users_comment(self):
        comment = self.make_comment()

        response = self.call(CommentDeleteView, 'delete', comment_id=comment.id)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Comment.objects.filter(id=comment.id).exists())

    def test_another_users_comment_is_not_deleted(self):
        comment = self.make_comment(user=self.other)

        response = self.call(CommentDeleteView, 'delete', comment_id=comment.id)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Comment.objects.filter(id=comment.id).exists())

    def test_unknown_comment_is_404(self):
        response = self.call(CommentDeleteView, 'delete', comment_id=999)

        self.assertEqual(response.status_code, 404)

    def test_deleting_a_comment_removes_its_likes(self):
        comment = self.make_comment()
        Like.objects.create(user=self.other, comment=comment)

        self.call(CommentDeleteView, 'delete', comment_id=comment.id)

        self.assertEqual(Like.objects.count(), 0)


class LikeViewTests(CommentViewTestCase):
    def test_requires_authentication(self):
        comment = self.make_comment()

        response = self.call(LikeView, 'post', user=False, comment_id=comment.id)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Like.objects.count(), 0)

    def test_likes_a_comment(self):
        comment = self.make_comment(user=self.other)

        response = self.call(LikeView, 'post', comment_id=comment.id)

        self.assertEqual(response.status_code, 201)
        like = Like.objects.get()
        self.assertEqual(like.user, self.user)
        self.assertEqual(like.comment, comment)
        comment.refresh_from_db()
        self.assertEqual(comment.like_count, 1)

    def test_liking_twice_keeps_one_like(self):
        comment = self.make_comment(user=self.other)

        self.call(LikeView, 'post', comment_id=comment.id)
        response = self.call(LikeView, 'post', comment_id=comment.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Like.objects.count(), 1)
        comment.refresh_from_db()
        self.assertEqual(comment.like_count, 1)

    def test_unknown_comment_is_404(self):
        response = self.call(LikeView, 'post', comment_id=999)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Like.objects.count(), 0)


class UnlikeViewTests(CommentViewTestCase):
    def test_requires_authentication(self):
        comment = self.make_comment()
        Like.objects.create(user=self.user, comment=comment)

        response = self.call(UnlikeView, 'delete', user=False, comment_id=comment.id)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Like.objects.count(), 1)

    def test_removes_the_users_like(self):
        comment = self.make_comment()
        self.call(LikeView, 'post', comment_id=comment.id)

        response = self.call(UnlikeView, 'delete', comment_id=comment.id)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(Like.objects.count(), 0)
        comment.refresh_from_db()
        self.assertEqual(comment.like_count, 0)

    def test_other_users_likes_are_kept(self):
        comment = self.make_comment()
        self.call(LikeView, 'post', user=self.other, comment_id=comment.id)

        self.call(UnlikeView, 'delete', comment_id=comment.id)

        self.assertEqual(Like.objects.count(), 1)
        comment.refresh_from_db()
        self.assertEqual(comment.like_count, 1)

    def test_unliking_without_a_like_keeps_the_count(self):
        comment = self.make_comment()

        self.call(UnlikeView, 'delete', comment_id=comment.id)

        comment.refresh_from_db()
        self.assertEqual(comment.like_count, 0)

    def test_unknown_comment_is_404(self):
        response = self.call(UnlikeView, 'delete', comment_id=999)

        self.assertEqual(response.status_code, 404)


class CommentThrottleScopeTests(ProblemsTestCase):
    def test_comment_and_like_scopes_are_configured(self):
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']

        for view in (CommentView, CommentPatchView, CommentDeleteView, LikeView, UnlikeView):
            with self.subTest(view=view.__name__):
                self.assertIn(view.throttle_scope, rates)


class CommentModelTests(CommentViewTestCase):
    def test_comments_and_likes_outlive_their_user(self):
        comment = self.make_comment(user=self.other)
        like = Like.objects.create(user=self.other, comment=comment)

        self.other.delete()
        comment.refresh_from_db()
        like.refresh_from_db()

        self.assertIsNone(comment.user)
        self.assertEqual(str(comment), '[deleted]-Nice problem')
        self.assertTrue(str(like).startswith('[deleted]-'))


class ProblemDetailCommentsTests(CommentViewTestCase):
    def get_comments(self, user=None):
        self.client.force_authenticate(user or self.user)
        response = self.client.get(f'/api/problems/{self.problem.id}/')
        self.assertEqual(response.status_code, 200)
        return response.data['comments']

    def test_problem_detail_lists_its_comments(self):
        comment = self.make_comment()
        self.call(LikeView, 'post', comment_id=comment.id)
        comment.refresh_from_db()

        comments = self.get_comments()

        self.assertEqual(
            comments,
            [{
                'id': comment.id,
                'text': 'Nice problem',
                'like_count': 1,
                'liked_by_me': True,
                'created_at': comment.created_at.isoformat().replace('+00:00', 'Z'),
            }],
        )

    def test_liked_by_me_is_false_when_only_others_liked(self):
        comment = self.make_comment()
        self.call(LikeView, 'post', user=self.other, comment_id=comment.id)

        comments = self.get_comments()

        self.assertFalse(comments[0]['liked_by_me'])
        self.assertEqual(comments[0]['like_count'], 1)

    def test_liked_by_me_is_per_viewer(self):
        liked = self.make_comment(text='liked')
        not_liked = self.make_comment(text='not liked')
        self.call(LikeView, 'post', user=self.other, comment_id=liked.id)

        comments = {c['id']: c['liked_by_me'] for c in self.get_comments(user=self.other)}

        self.assertEqual(comments, {liked.id: True, not_liked.id: False})

    def test_query_count_does_not_grow_with_comments(self):
        self.make_comment()
        with self.assertNumQueries(3):
            self.get_comments()

        for i in range(5):
            comment = self.make_comment(text=f'c{i}')
            Like.objects.create(user=self.user, comment=comment)
        with self.assertNumQueries(3):
            self.get_comments()
