from django.conf import settings
from django.db import IntegrityError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError

from . import services
from .authentication import enforce_csrf
from .cookies import clear_auth_cookies, set_auth_cookies
from .serializers import LoginSerializer, PublicUserSerializer, SignupSerializer


class PublicAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        enforce_csrf(request)


@method_decorator(
    sensitive_post_parameters('password', 'password_confirmation'), name='dispatch'
)
class SignupView(PublicAPIView):
    throttle_scope = 'auth-signup'

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            user = services.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password'],
                timezone=data['timezone'],
            )
        except IntegrityError:
            raise ValidationError({'detail': 'That username or email is already taken.'})

        access, refresh = services.issue_tokens(user)
        response = Response(PublicUserSerializer(user).data, status=status.HTTP_201_CREATED)
        return set_auth_cookies(response, access, refresh)


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class LoginView(PublicAPIView):
    throttle_scope = 'auth-login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = services.authenticate_user(
            identifier=data['identifier'],
            password=data['password'],
        )
        if user is None:
            return Response(
                {'detail': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        access, refresh = services.issue_tokens(user)
        response = Response(PublicUserSerializer(user).data, status=status.HTTP_200_OK)
        return set_auth_cookies(response, access, refresh)


class RefreshView(PublicAPIView):
    throttle_scope = 'auth-refresh'

    def post(self, request):
        raw_refresh = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        try:
            access, refresh, user = services.rotate_refresh_token(raw_refresh)
        except TokenError:
            response = Response(
                {'detail': 'Invalid or expired refresh token.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            return clear_auth_cookies(response)

        response = Response(PublicUserSerializer(user).data, status=status.HTTP_200_OK)
        return set_auth_cookies(response, access, refresh)


class LogoutView(PublicAPIView):
    def post(self, request):
        services.blacklist_refresh_token(request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        return clear_auth_cookies(response)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PublicUserSerializer(request.user).data)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(PublicAPIView):
    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)
