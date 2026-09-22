from django.urls import path
from .views import ProblemListView, ProblemDetailView, SubmissionDetailsView, SubmitView

urlpatterns = [
    path('problems/', ProblemListView.as_view()),
    path('problems/<uuid:problem_id>/', ProblemDetailView.as_view()),
    path('problems/<uuid:problem_id>/submit/', SubmitView.as_view()),
    path('problems/score/', SubmissionDetailsView.as_view()),
]