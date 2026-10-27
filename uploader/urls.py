from django.urls import path
from .views import UploadProblemView, UploadProblemDetailView, UpdateUploadedProblemView, UpdatesHistoryView

urlpatterns = [
    path('uploader/problem/', UploadProblemView.as_view()),
    path('uploader/problem/<uuid:problem_id>/content/', UploadProblemDetailView.as_view()),
    path('uploader/content/<uuid:problem_file_id>/update/', UpdateUploadedProblemView.as_view()),
    path('uploader/history/', UpdatesHistoryView.as_view()),
]