from django.urls import path
from .views import ReportExportView

urlpatterns = [
    path('export/', ReportExportView.as_view(), name='report-export'),
]