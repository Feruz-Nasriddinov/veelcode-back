from django.urls import path

from .views import CsrfView, LoginView, LogoutView, MeView, RefreshView, SignupView

urlpatterns = [
    path('signup/', SignupView.as_view()),
    path('login/', LoginView.as_view()),
    path('refresh/', RefreshView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('me/', MeView.as_view()),
    path('csrf/', CsrfView.as_view()),
]
