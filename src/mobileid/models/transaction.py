from django.db import models

from core.models import ProjectControlModel


class Transaction(ProjectControlModel):
    """
    Usage log tying members and barcodes.
    """

    model_user = models.ForeignKey("authn.Member", on_delete=models.CASCADE)
    barcode_used = models.ForeignKey("mobileid.Barcode", on_delete=models.CASCADE)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        db_table = "authn_transaction"

    def __str__(self):
        return f"{self.model_user.username} used {self.barcode_used} @ {self.created_at}"
