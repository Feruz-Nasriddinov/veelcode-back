from django.urls import path

from .views import ActivityView, ProfileView

urlpatterns = [
    path('profile/', ProfileView.as_view()),
    path('profile/activity/', ActivityView.as_view()),
]
