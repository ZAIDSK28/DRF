from django.urls import path ,include
from rest_framework.routers import DefaultRouter
from .views import LoginView, LogoutView ,UserViewSet, VerifyOTPView


router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('', include(router.urls)), 
    path('login/', LoginView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='token_blacklist'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
]
