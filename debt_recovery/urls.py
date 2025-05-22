from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView  # ✅ Add this
from rest_framework.routers import DefaultRouter
from bills.views import RouteViewSet, OutletViewSet



router = DefaultRouter()
router.register(r'routes', RouteViewSet, basename='route')
router.register(r'outlets', OutletViewSet, basename='outlet')



urlpatterns = [
    path('api/', include(router.urls)),
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/auth/', include('users.urls')),
    path('api/bills/', include('bills.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/reports/', include('bills.urls_reports')),  
]