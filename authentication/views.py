import hmac
import secrets

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
from .cookies import (
    clear_auth_cookies,
    clear_oauth_state_cookie,
    set_auth_cookies,
    set_oauth_state_cookie,
)
from .oauth import OAuthError
from .serializers import (
    LoginSerializer,
    OAuthCodeSerializer,
    PublicUserSerializer,
    SignupSerializer,
)


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
            raise ValidationError({'detail': 'That username or email is unavailable.'})

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


@method_decorator(sensitive_post_parameters('code'), name='dispatch')
class SocialLoginView(PublicAPIView):
    throttle_scope = 'auth-social'
    provider = None

    def post(self, request):
        serializer = OAuthCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        expected_state = request.COOKIES.get(settings.OAUTH_STATE_COOKIE_NAME, '')
        if not expected_state or not hmac.compare_digest(
            expected_state.encode(), serializer.validated_data['state'].encode()
        ):
            return clear_oauth_state_cookie(
                Response({'detail': 'Invalid login state.'}, status=status.HTTP_400_BAD_REQUEST)
            )

        try:
            user = services.authenticate_social_user(
                provider=self.provider,
                code=serializer.validated_data['code'],
            )
        except OAuthError as exc:
            return clear_oauth_state_cookie(
                Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            )
        except IntegrityError:
            raise ValidationError({'detail': 'That username or email is already taken.'})

        access, refresh = services.issue_tokens(user)
        response = Response(PublicUserSerializer(user).data, status=status.HTTP_200_OK)
        return clear_oauth_state_cookie(set_auth_cookies(response, access, refresh))


class OAuthStateView(PublicAPIView):
    throttle_scope = 'auth-state'

    def get(self, request):
        state = secrets.token_urlsafe(32)
        return set_oauth_state_cookie(Response({'state': state}), state)


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
        services.revoke_access_token(request.COOKIES.get(settings.AUTH_ACCESS_COOKIE_NAME))
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
