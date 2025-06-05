from django.urls import path
from .views import BillPaymentsListCreateView, MyPaymentsListView , TodayPaymentTotalsAPIView

urlpatterns = [
    path('', MyPaymentsListView.as_view(), name='my-payments'),
    path('<int:bill_id>/payments/', BillPaymentsListCreateView.as_view(), name='bill-payments'),
    path(
        "today-totals/",
        TodayPaymentTotalsAPIView.as_view(),
        name="today-payment-totals",
    ),
]
