from rest_framework import permissions, viewsets

from ..models import Barcode, MobileID, Transaction
from ..serializers import BarcodeSerializer, MobileIDSerializer, TransactionSerializer


class BarcodeViewSet(viewsets.ModelViewSet):
    """
    CRUD for member barcodes.
    """

    queryset = Barcode.objects.select_related("model_user").all()
    serializer_class = BarcodeSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]


class MobileIDViewSet(viewsets.ModelViewSet):
    """
    CRUD for mobile IDs bound to barcodes.
    """

    queryset = MobileID.objects.select_related("model_user", "user_barcode").all()
    serializer_class = MobileIDSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only transaction log.
    """

    queryset = Transaction.objects.select_related("model_user", "barcode_used").all()
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "options"]
