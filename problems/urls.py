from django.urls import path
from .views import ProblemListView, ProblemDetailView, SubmissionHistoryView, SubmitView, SubmissionDetailView

urlpatterns = [
    path('problems/', ProblemListView.as_view()),
    path('problems/<uuid:problem_id>/', ProblemDetailView.as_view()),
    path('problems/<uuid:problem_id>/submit/', SubmitView.as_view()),
    path('problems/<uuid:submission_id>/score/', SubmissionDetailView.as_view()),
    path('problems/history/', SubmissionHistoryView.as_view()),
]