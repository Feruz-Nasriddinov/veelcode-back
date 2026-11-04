from django.urls import path
from .views import (
    ProblemListView, ProblemDetailView, SubmissionHistoryView, SubmitView, SubmissionDetailView,
    CommentView, CommentPatchView, CommentDeleteView, LikeView, UnlikeView,
)

urlpatterns = [
    path('problems/', ProblemListView.as_view()),
    path('problems/<uuid:problem_id>/', ProblemDetailView.as_view()),
    path('problems/<uuid:problem_id>/submit/', SubmitView.as_view()),
    path('problems/<uuid:submission_id>/score/', SubmissionDetailView.as_view()),
    path('problems/history/', SubmissionHistoryView.as_view()),
    path('problems/<uuid:problem_id>/comments/', CommentView.as_view()),
    path('comments/<uuid:comment_id>/edit/', CommentPatchView.as_view()),
    path('comments/<uuid:comment_id>/delete/', CommentDeleteView.as_view()),
    path('comments/<uuid:comment_id>/like/', LikeView.as_view()),
    path('comments/<uuid:comment_id>/unlike/', UnlikeView.as_view()),
]
