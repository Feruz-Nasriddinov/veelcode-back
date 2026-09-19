from django.urls import path
from .views import UploadProblemView, UploadProblemDetailView

url_patterns = [
    path('uploader/problem', UploadProblemView.as_view()),
    path('uploader/problem/<uuid:problem_id>/content/', UploadProblemDetailView.as_view()),
]