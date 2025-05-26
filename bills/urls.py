from django.urls import path
from .views import (
    BillListCreateView, BillDetailView,
    BillAssignView, BillImportView ,MyAssignmentsFlatView
)

urlpatterns = [
    path('', BillListCreateView.as_view(), name='bills-list-create'),
    path('import/', BillImportView.as_view(), name='bills-import'),
    path('<int:pk>/', BillDetailView.as_view(), name='bills-detail'),
    path('<int:bill_id>/assign/', BillAssignView.as_view(), name='bills-assign'),
    path(
        'my-assignments-flat/',
        MyAssignmentsFlatView.as_view(),
        name='my-assignments-flat'
    ),
]