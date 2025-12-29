from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BarcodeViewSet, MobileIDViewSet, TransactionViewSet

app_name = "mobileid"

router = DefaultRouter()
router.register(r"barcodes", BarcodeViewSet, basename="barcode")
router.register(r"mobile-ids", MobileIDViewSet, basename="mobileid")
router.register(r"transactions", TransactionViewSet, basename="transaction")

urlpatterns = [
    path("", include(router.urls)),
]

