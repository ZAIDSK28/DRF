from django.urls import path ,include
from rest_framework.routers import DefaultRouter
from .views import LoginView, LogoutView ,UserViewSet


router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('', include(router.urls)), 
    path('login/', LoginView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='token_blacklist'),
]
