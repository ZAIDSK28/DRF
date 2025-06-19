from django.db.models import Q
from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.generics import GenericAPIView
from drf_spectacular.utils import extend_schema, OpenApiResponse
from users.serializers import LogoutRequestSerializer
from django.core.mail import send_mail
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from drf_spectacular.utils import extend_schema


from .models import User, AdminOTP
from users.serializers import UserSerializer, OTPVerifySerializer, TokenResponseSerializer


class LoginView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        # 1) Validate credentials
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user

        # 2) Admin? → email OTP instead of returning tokens
        if user.role == "admin":
            from users.models import AdminOTP
            otp = AdminOTP.generate_for(user)
            # send it
            send_mail(
                subject="Your Admin OTP",
                message=f"Your login OTP is: {otp.code}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
            return Response(
                {"detail": "OTP sent to your email.", "username": user.username},
                status=202
            )

        # 3) DRA flow → immediate token + user data
        refresh = serializer.validated_data["refresh"]
        access  = serializer.validated_data["access"]
        return Response({
            "refresh": str(refresh),
            "access":  str(access),
            "user":    UserSerializer(user).data,
        }, status=200)




class LogoutView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LogoutRequestSerializer

    @extend_schema(
        request   = LogoutRequestSerializer,
        responses = {204: OpenApiResponse(description="No content")},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data['refresh']

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            # invalid token or already blacklisted
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/auth/users/      → list non-admin users
    GET /api/auth/users/{pk}/ → retrieve single non-admin user
    """
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return User.objects.exclude(
            Q(is_superuser=True) | Q(role='admin')
        )

class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=OTPVerifySerializer,
        responses={200: TokenResponseSerializer},  # document your response shape
    )
    

    def post(self, request):
        ser = OTPVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        u   = ser.validated_data["username"]
        code= ser.validated_data["code"]

        try:
            user = User.objects.get(username=u, role="admin")
        except User.DoesNotExist:
            return Response({"detail":"Invalid user."}, status=400)

        try:
            otp = AdminOTP.objects.get(user=user, code=code, used=False)
        except AdminOTP.DoesNotExist:
            return Response({"detail":"Invalid or used OTP."}, status=400)

        if otp.is_expired():
            otp.used = True
            otp.save(update_fields=["used"])
            return Response({"detail":"OTP expired."}, status=400)

        # mark used
        otp.used = True
        otp.save(update_fields=["used"])

        # now issue tokens
        refresh = RefreshToken.for_user(user)
        access  = refresh.access_token

        return Response({
            "refresh": str(refresh),
            "access":  str(access),
            "user":    UserSerializer(user).data,
        }, status=200)