from django.db.models import Exists, OuterRef

from problems.models import Comment, Like


def comments_for_viewer(user):
    return Comment.objects.select_related('user').annotate(
        liked_by_me=Exists(
            Like.objects.filter(comment=OuterRef('pk'), user=user)
        )
    )
