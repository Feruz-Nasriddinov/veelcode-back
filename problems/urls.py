from django.urls import path
from .views import ProblemListView, ProblemDetailView, ScoreView

urlpatterns = [
    path('problems/', ProblemListView.as_view()),
    path('problems/<uuid:problem_id>/', ProblemDetailView.as_view()),
    path('problems/<uuid:problem_id>/score/', ScoreView.as_view()),
]