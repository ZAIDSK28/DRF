# debt_recovery/urls.py

from django.contrib import admin
from django.urls import path, include   
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from bills.views import (
    RouteViewSet,
    OutletViewSet,
    # BillExportView,      # import new export view for bills
    # PaymentExportView,   # import new export view for payments
)

router = DefaultRouter()
router.register(r'routes',  RouteViewSet,  basename='route')
router.register(r'outlets', OutletViewSet, basename='outlet')



urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/bills/', include('bills.urls')),
    # path(
    #     "api/bills/export-bills/",
    #     BillExportView.as_view(),
    #     name="export-bills",
    # ),
    # path(
    #     "api/bills/export-payments/",
    #     PaymentExportView.as_view(),
    #     name="export-payments",
    # ),
    path('api/auth/', include('users.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/',   SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
