from rest_framework import serializers
from users.models import User


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.ReadOnlyField()
    class Meta:
        model = User
        fields = ('id','username','full_name','role','is_admin')
