from rest_framework import generics, permissions
from django.shortcuts import get_object_or_404
from bills.models import Bill
from .models import Payment
from .serializers import PaymentSerializer, PaymentCreateSerializer

class IsDRA(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'dra'

# 10 & 11. List & Create payments for a bill
class BillPaymentsListCreateView(generics.ListCreateAPIView):
    serializer_class = PaymentSerializer
    permission_classes = (IsDRA,)

    def get_queryset(self):
        bid = self.kwargs['bill_id']
        return Payment.objects.filter(bill__id=bid, dra=self.request.user)

    def perform_create(self, serializer):
        bill = get_object_or_404(Bill, pk=self.kwargs['bill_id'])
        payment = serializer.save(dra=self.request.user, bill=bill)
        if bill.amount <= 0:
            bill.status = 'cleared'
        bill.save()

# 13. List all my payments
class MyPaymentsListView(generics.ListAPIView):
    serializer_class   = PaymentSerializer
    # permission_classes = (IsDRA,IsAdmin)

    def get_queryset(self):
        # only payments for bills that are assigned to the logged-in user
        return Payment.objects.filter(bill__assigned_to=self.request.user)