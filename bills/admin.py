# bills/admin.py
from django.contrib import admin
from .models import Route, Outlet, Bill

class OutletInline(admin.TabularInline):
    model = Outlet
    extra = 1  # “Add another Outlet” row

@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display  = ("pk","name", "outlet_count")
    search_fields = ("name",)
    inlines       = (OutletInline,)

    def outlet_count(self, obj):
        return obj.outlets.count()
    outlet_count.short_description = "Outlets"


@admin.register(Outlet)
class OutletAdmin(admin.ModelAdmin):
    list_display  = ("pk","name", "route")
    list_filter   = ("route",)
    search_fields = ("name", "route__name")


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ("pk","invoice_number", "outlet", "route", "amount","remaining_amount", "status")
    list_filter  = ("outlet__route", "status", "brand")
    search_fields = ("invoice_number", "outlet__name",)
    readonly_fields = ('remaining_amount','amount')
    list_per_page = 25
