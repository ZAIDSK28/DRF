import random, string
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils import timezone

class User(AbstractUser):
    ROLE_CHOICES = (('admin', 'Admin'), ('dra', 'Debt Recovery Agent'))
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    full_name = models.CharField(max_length=255)

    @property
    def is_admin(self):
        return self.role == 'admin'


class AdminOTP(models.Model):
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code       = models.CharField(max_length=6)       # e.g. “482915”
    created_at = models.DateTimeField(auto_now_add=True)
    used       = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "code"]),
        ]

    def is_expired(self):
        # valid for 5 minutes
        return timezone.now() > (self.created_at + timezone.timedelta(minutes=5))

    @classmethod
    def generate_for(cls, user):
        # create a fresh one, mark any others used
        cls.objects.filter(user=user, used=False).update(used=True)
        code = "".join(random.choices(string.digits, k=6))
        return cls.objects.create(user=user, code=code)