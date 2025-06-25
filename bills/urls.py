# bills/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from bills.views import (
    BillListCreateView,
    BillDetailView,
    BillImportView,
    BillAssignView,
    MyAssignmentsFlatView,
    ImportBillsFromExcelAPIView,
    BillExportView,
    PaymentExportView,
)

router = DefaultRouter()

urlpatterns = [
    # GET  /api/bills/                → BillListCreateView
    path("", BillListCreateView.as_view(), name="bills-list-create"),

    # POST /api/bills/import/         → BillImportView
    path("import/", BillImportView.as_view(), name="bills-import"),

    # GET  /api/bills/<pk>/           → BillDetailView
    path("<int:pk>/", BillDetailView.as_view(), name="bills-detail"),

    # PUT  /api/bills/<bill_id>/assign/ → BillAssignView
    path("<int:bill_id>/assign/", BillAssignView.as_view(), name="bills-assign"),

    # GET  /api/bills/my-assignments-flat/ → MyAssignmentsFlatView
    path("my-assignments-flat/", MyAssignmentsFlatView.as_view(), name="my-assignments-flat"),

    # GET  /api/bills/export-records/
    # Note: no “bills/” prefix here—just “export-records/”

    # If you want to expose the “categories” router under /api/bills/categories/…
    path("", include(router.urls)),

    path("import-excel/", ImportBillsFromExcelAPIView.as_view(), name="import-bills-excel"),

    path("export-bills/", BillExportView.as_view(), name="export-bills"),
    path("export-payments/", PaymentExportView.as_view(), name="export-payments"),
]
