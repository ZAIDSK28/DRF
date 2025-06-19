# users/serializers.py
from rest_framework import serializers
from users.models import User


class LogoutRequestSerializer(serializers.Serializer):
    """POST body for /api/auth/logout/."""
    refresh = serializers.CharField()

class UserSerializer(serializers.ModelSerializer):
    # DRF will automatically look for a model attribute/property
    # with the same name, so no `source=` is required.
    is_admin = serializers.BooleanField(read_only=True)

    class Meta:
        model  = User
        fields = ('id', 'username', 'full_name', 'role', 'is_admin')

class OTPVerifySerializer(serializers.Serializer):
    username = serializers.CharField()
    code     = serializers.CharField(max_length=6)

class TokenResponseSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access  = serializers.CharField()
    user    = UserSerializer()
