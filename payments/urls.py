from django.urls import path
from .views import BillPaymentsListCreateView, MyPaymentsListView

urlpatterns = [
    path('', MyPaymentsListView.as_view(), name='my-payments'),
    path('<int:bill_id>/payments/', BillPaymentsListCreateView.as_view(), name='bill-payments'),
]
