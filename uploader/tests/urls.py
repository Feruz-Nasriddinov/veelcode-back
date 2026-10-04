from django.urls import include, path

from uploader.views import UpdateUploadedProblemView, UploadProblemDetailView, UploadProblemView

urlpatterns = [
    path('api/auth/', include('authentication.urls')),
    path('api/uploader/problem/', UploadProblemView.as_view()),
    path('api/uploader/problem/<uuid:problem_id>/content/', UploadProblemDetailView.as_view()),
    path('api/uploader/content/<int:problem_file_id>/update/', UpdateUploadedProblemView.as_view()),
]
