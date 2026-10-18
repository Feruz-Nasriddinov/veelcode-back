from django.urls import path

from users.models import SocialAccount

from .views import (
    CsrfView,
    LoginView,
    LogoutView,
    MeView,
    OAuthStateView,
    RefreshView,
    SignupView,
    SocialLoginView,
)

urlpatterns = [
    path('signup/', SignupView.as_view()),
    path('login/', LoginView.as_view()),
    path('google/', SocialLoginView.as_view(provider=SocialAccount.GOOGLE)),
    path('github/', SocialLoginView.as_view(provider=SocialAccount.GITHUB)),
    path('oauth-state/', OAuthStateView.as_view()),
    path('refresh/', RefreshView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('me/', MeView.as_view()),
    path('csrf/', CsrfView.as_view()),
]
