from bills.serializers import serializers
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from django.db.models.functions import Coalesce
from django.db.models import Sum, Q, Value, DecimalField
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.generics import GenericAPIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes


from django.utils.dateparse import parse_date
from django.utils import timezone
from bills.models import Bill
from .models import Payment
from .serializers import PaymentSerializer, TodayPaymentTotalsSerializer
from rest_framework.permissions import IsAdminUser
from .pagination import PaymentPagination
from .serializers import *



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
        qs = Payment.objects.exclude(
            Q(payment_method__in=["cheque","electronic"]) &
            Q(cheque_status__in=["pending", "bounced"])
        ).order_by('-created_at')
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

class TodayPaymentTotalsAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        today = timezone.localdate()

        cash_sum = Payment.objects.filter(
            payment_method="cash",
            created_at__date=today
        ).aggregate(
            total=Coalesce(
                Sum("amount"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        upi_sum = Payment.objects.filter(
            payment_method="upi",
            created_at__date=today
        ).aggregate(
            total=Coalesce(
                Sum("amount"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        cheque_sum = Payment.objects.filter(
            payment_method__in=["cheque", "electronic"],
            cheque_status="cleared",
            cheque_date=today
        ).aggregate(
            total=Coalesce(
                Sum("amount"),
                Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )["total"]

        return Response({
            "date":        today,
            "cash_total":  cash_sum,
            "upi_total":   upi_sum,
            "cheque_total": cheque_sum,
        })

class ChequeHistoryAPIView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = PaymentSerializer
    pagination_class   = PaymentPagination


    @extend_schema(
        parameters=[
            OpenApiParameter("invoice_number", OpenApiTypes.STR, required=False),
            OpenApiParameter("page",           OpenApiTypes.INT, required=False),
            OpenApiParameter("limit",          OpenApiTypes.INT, required=False),
        ],
    )

    def get(self, request, pk=None, format=None):
        METHODS = ["cheque", "electronic"]
        if request.user.is_staff:
           base_qs = Payment.objects.filter(payment_method__in=METHODS)
        else:
           base_qs = Payment.objects.filter(
                dra=request.user,
                payment_method__in=METHODS
            )

        # 2) detail vs list
        if pk is not None:
            payment = get_object_or_404(base_qs, pk=pk)
            return Response(PaymentSerializer(payment).data)

        # 3) optional expired filter
        if request.query_params.get("expired") == "true":
            today = timezone.localdate()
            base_qs = base_qs.filter(
                cheque_date__lt=today,
                cheque_status="pending"
            )

        # invoice-number search
        inv = request.query_params.get("invoice_number")
        if inv:
            base_qs = base_qs.filter(bill__invoice_number__icontains=inv)

        # now paginate & return
        qs = base_qs.order_by("-cheque_date")
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = self.get_serializer(page, many=True)
            return self.get_paginated_response(ser.data)

        # fallback (no page/limit)
        ser = self.get_serializer(qs, many=True)
        return Response(ser.data)

    @extend_schema(
        request=ChequeStatusSerializer,
        responses={200: PaymentSerializer},
    )
    def put(self, request, pk, format=None):
        if not request.user.is_staff:
            return Response(
                {"detail": "Only admins may update cheque status."},
                status=status.HTTP_403_FORBIDDEN
            )

        # now allow both cheque _and_ electronic
        payment = get_object_or_404(
            Payment.objects.filter(payment_method__in=["cheque", "electronic"]),
            pk=pk
        )

        ser = ChequeStatusSerializer(payment, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()

        # stamp today as the “cleared” date
        if ser.validated_data.get("cheque_status") == "cleared":
            payment.cheque_date = timezone.localdate()
            payment.save(update_fields=["cheque_date"])

        # update linked Bill
        bill = payment.bill
        new = ser.validated_data["cheque_status"]
        if new == "bounced":
            bill.remaining_amount += payment.amount
            bill.status = "open"
            bill.save(update_fields=["remaining_amount", "status"])
        elif new == "cleared" and bill.remaining_amount <= 0:
            bill.status = "closed"
            bill.save(update_fields=["status"])

        return Response(ser.data, status=status.HTTP_200_OK)
    def delete(self, request, pk, format=None):
        """
        DELETE /api/payments/cheque-history/{pk}/
        → hard-delete the cheque payment record.
        """
        # 1) Optional: restrict to admins only
        if not request.user.is_staff:
            return Response(
                {"detail": "Only admins may delete payments."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2) Fetch & delete
        payment = get_object_or_404(
            Payment.objects.filter(payment_method="cheque"),
            pk=pk
        )
        payment.delete()

        # 3) 204 No Content on success
        return Response(status=status.HTTP_204_NO_CONTENT)

