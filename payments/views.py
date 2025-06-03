from bills.serializers import serializers
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date

from bills.models import Bill
from .models import Payment
from .serializers import PaymentSerializer
from rest_framework.permissions import IsAdminUser
from .pagination import PaymentPagination


class IsDRA(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'dra'


class BillPaymentsListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/payments/<bill_id>/payments/
      → list all payments for bill=<bill_id>, made by the current DRA.
      If neither `page` nor `limit` is provided, returns all matching payments.
      Supports filters:
        • ?invoice_number=<str>  → filters Payment → Bill → invoice_number__icontains
        • ?start_date=YYYY-MM-DD → filters Payment.created_at__date >= start_date
        • ?end_date=YYYY-MM-DD   → filters Payment.created_at__date <= end_date

    POST /api/payments/<bill_id>/payments/
      → create a new payment (assigned to the current DRA & this bill).
    """
    serializer_class = PaymentSerializer
    permission_classes = (IsDRA,)
    pagination_class = PaymentPagination

    def get_queryset(self):
        bid = self.kwargs['bill_id']

        # 1) Base: payments belonging to this bill and this DRA
        qs = Payment.objects.filter(bill__id=bid, dra=self.request.user)

        # 2) Filter by invoice_number (Payment → Bill → invoice_number)
        inv_no = self.request.query_params.get('invoice_number')
        if inv_no:
            qs = qs.filter(bill__invoice_number__icontains=inv_no)

        # 3) Filter by payment date range (created_at date)
        raw_start = self.request.query_params.get('start_date')
        raw_end = self.request.query_params.get('end_date')
        start_date = parse_date(raw_start) if raw_start else None
        end_date = parse_date(raw_end) if raw_end else None

        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        return qs.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        """
        If neither `page` nor `limit` in query params, return ALL matching payments.
        Otherwise, fall back to DRF pagination.
        """
        if 'page' not in request.query_params and 'limit' not in request.query_params:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        """
        At this point, `validate_amount()` in the serializer has already run,
        so `amount <= bill.remaining_amount` and `remaining_amount > 0` are guaranteed.
        """
        bill = get_object_or_404(Bill, pk=self.kwargs['bill_id'])
        payment = serializer.save(dra=self.request.user, bill=bill)

        # If fully paid now, mark as cleared
        if bill.remaining_amount <= 0:
            bill.status = 'cleared'
            bill.save()


class MyPaymentsListView(generics.ListAPIView):
    """
    GET /api/payments/ → list ALL payments (admin only).
      If neither `page` nor `limit` is provided, returns ALL matching payments.
      Supports filters:
        • ?invoice_number=<str>  → Payment → Bill → invoice_number__icontains
        • ?username=<str>        → Payment → dra → username__icontains
        • ?start_date=YYYY-MM-DD → Payment.created_at__date >= start_date
        • ?end_date=YYYY-MM-DD   → Payment.created_at__date <= end_date
    """
    serializer_class = PaymentSerializer
    permission_classes = (IsAdminUser,)
    pagination_class = PaymentPagination

    def get_queryset(self):
        # Base: all payments, ordered newest first
        qs = Payment.objects.all().order_by('-created_at')

        # Filter by invoice_number
        inv_no = self.request.query_params.get('invoice_number')
        if inv_no:
            qs = qs.filter(bill__invoice_number__icontains=inv_no)

        # Filter by Dra username
        uname = self.request.query_params.get('username')
        if uname:
            qs = qs.filter(dra__username__icontains=uname)

        # Filter by payment date range
        raw_start = self.request.query_params.get('start_date')
        raw_end = self.request.query_params.get('end_date')
        start_date = parse_date(raw_start) if raw_start else None
        end_date = parse_date(raw_end) if raw_end else None

        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        return qs

    def list(self, request, *args, **kwargs):
        """
        Override `list()` so that if neither `page` nor `limit` is present, 
        we return the full queryset; otherwise, use standard pagination.
        """
        if 'page' not in request.query_params and 'limit' not in request.query_params:
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return super().list(request, *args, **kwargs)
