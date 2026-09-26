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

    def expected_comment(self, comment, like_count=0, liked_by_me=False, author=None):
        author = author or self.user
        return {
            'id': comment.id,
            'text': comment.text,
            'like_count': like_count,
            'liked_by_me': liked_by_me,
            'created_at': comment.created_at.isoformat().replace('+00:00', 'Z'),
            'user': {'id': author.id, 'username': author.username},
        }


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
        self.assertEqual(response.data, self.expected_comment(comment))

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

    def test_problem_that_is_not_accepted_is_404(self):
        pending = self.make_problem(status='pending')

        response = self.call(CommentView, 'post', {'text': 'hi'}, problem_id=pending.id)

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
        comment.refresh_from_db()
        self.assertEqual(comment.text, 'edited')
        self.assertEqual(response.data, self.expected_comment(comment))

    def test_the_response_keeps_the_authors_own_like(self):
        comment = self.make_comment()
        self.call(LikeView, 'post', comment_id=comment.id)

        response = self.call(CommentPatchView, 'patch', {'text': 'edited'}, comment_id=comment.id)

        self.assertTrue(response.data['liked_by_me'])
        self.assertEqual(response.data['like_count'], 1)

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

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'liked': True, 'like_count': 1})
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
        self.assertEqual(response.data, {'liked': True, 'like_count': 1})
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

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'liked': False, 'like_count': 0})
        self.assertEqual(Like.objects.count(), 0)
        comment.refresh_from_db()
        self.assertEqual(comment.like_count, 0)

    def test_other_users_likes_are_kept(self):
        comment = self.make_comment()
        self.call(LikeView, 'post', user=self.other, comment_id=comment.id)

        response = self.call(UnlikeView, 'delete', comment_id=comment.id)

        self.assertEqual(response.data, {'liked': False, 'like_count': 1})
        self.assertEqual(Like.objects.count(), 1)
        comment.refresh_from_db()
        self.assertEqual(comment.like_count, 1)

    def test_unliking_without_a_like_keeps_the_count(self):
        comment = self.make_comment()

        response = self.call(UnlikeView, 'delete', comment_id=comment.id)

        self.assertEqual(response.data, {'liked': False, 'like_count': 0})
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

        self.assertIn('comments-read', rates)


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


class ProblemDetailCommentCountTests(CommentViewTestCase):
    def get_detail(self, user=None):
        self.client.force_authenticate(user or self.user)
        response = self.client.get(f'/api/problems/{self.problem.id}/')
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_detail_reports_the_comment_count(self):
        self.make_comment()
        self.make_comment(text='second')

        self.assertEqual(self.get_detail()['comment_count'], 2)

    def test_count_is_zero_without_comments(self):
        self.assertEqual(self.get_detail()['comment_count'], 0)

    def test_detail_no_longer_carries_the_thread(self):
        self.make_comment()

        self.assertNotIn('comments', self.get_detail())

    def test_query_count_does_not_grow_with_comments(self):
        with self.assertNumQueries(2):
            self.get_detail()

        for i in range(5):
            self.make_comment(text=f'c{i}')

        with self.assertNumQueries(2):
            self.get_detail()


class CommentListViewTests(CommentViewTestCase):
    def list(self, user=None, problem_id=None, **params):
        return self.call(
            CommentView,
            'get',
            params or None,
            user=user,
            problem_id=problem_id or self.problem.id,
        )

    def test_requires_authentication(self):
        self.make_comment()

        response = self.list(user=False)

        self.assertEqual(response.status_code, 401)

    def test_lists_the_problems_comments(self):
        comment = self.make_comment()
        self.call(LikeView, 'post', comment_id=comment.id)
        comment.refresh_from_db()

        response = self.list()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertIsNone(response.data['next'])
        self.assertIsNone(response.data['previous'])
        self.assertEqual(
            response.data['results'],
            [self.expected_comment(comment, like_count=1, liked_by_me=True)],
        )

    def test_newest_comment_comes_first(self):
        self.make_comment(text='first')
        self.make_comment(text='second')
        self.make_comment(text='third')

        response = self.list()

        self.assertEqual(
            [comment['text'] for comment in response.data['results']],
            ['third', 'second', 'first'],
        )

    def test_comments_are_paginated(self):
        for i in range(21):
            self.make_comment(text=f'c{i}')

        first = self.list()
        second = self.list(page=2)

        self.assertEqual(first.data['count'], 21)
        self.assertEqual(len(first.data['results']), 20)
        self.assertIsNotNone(first.data['next'])
        self.assertEqual(first.data['results'][0]['text'], 'c20')
        self.assertEqual([c['text'] for c in second.data['results']], ['c0'])

    def test_another_problems_comments_are_not_listed(self):
        other_problem = self.make_problem(title='Another problem')
        Comment.objects.create(user=self.user, problem=other_problem, text='elsewhere')
        mine = self.make_comment()

        response = self.list()

        self.assertEqual([c['id'] for c in response.data['results']], [mine.id])

    def test_liked_by_me_is_per_viewer(self):
        liked = self.make_comment(text='liked')
        not_liked = self.make_comment(text='not liked')
        self.call(LikeView, 'post', user=self.other, comment_id=liked.id)

        results = self.list(user=self.other).data['results']

        self.assertEqual(
            {c['id']: c['liked_by_me'] for c in results},
            {liked.id: True, not_liked.id: False},
        )

    def test_liked_by_me_is_false_when_only_others_liked(self):
        comment = self.make_comment()
        self.call(LikeView, 'post', user=self.other, comment_id=comment.id)

        listed = self.list().data['results'][0]

        self.assertFalse(listed['liked_by_me'])
        self.assertEqual(listed['like_count'], 1)

    def test_author_is_null_after_the_user_is_deleted(self):
        self.make_comment(user=self.other)
        self.other.delete()

        self.assertIsNone(self.list().data['results'][0]['user'])

    def test_query_count_does_not_grow_with_comments(self):
        self.make_comment()
        with self.assertNumQueries(3):
            self.list()

        for i in range(5):
            author = User.objects.create_user(
                username=f'author{i}', email=f'author{i}@example.com', password=PASSWORD
            )
            comment = self.make_comment(user=author, text=f'c{i}')
            Like.objects.create(user=self.user, comment=comment)

        with self.assertNumQueries(3):
            self.list()

    def test_unknown_problem_is_404(self):
        response = self.list(problem_id=uuid.uuid4())

        self.assertEqual(response.status_code, 404)

    def test_problem_that_is_not_accepted_is_404(self):
        pending = self.make_problem(status='pending')
        Comment.objects.create(user=self.user, problem=pending, text='hidden')

        response = self.list(problem_id=pending.id)

        self.assertEqual(response.status_code, 404)
