from django.db.models import Q
from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from users.models import User
from users.serializers import UserSerializer


class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/  ->  returns refresh, access and user info
    """
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user    = serializer.user
        refresh = serializer.validated_data["refresh"]
        access  = serializer.validated_data["access"]

        return Response({
            "refresh": str(refresh),
            "access":  str(access),
            "user":    UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            # invalid token, or already blacklisted
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/auth/users/       → list all non-admin users
    GET /api/auth/users/{pk}/  → retrieve a single non-admin user
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # exclude both Django superusers and any user whose role is 'admin'
        return User.objects.exclude(
            Q(is_superuser=True) |
            Q(role='admin')
        )