from django.db import models

from core.models.base import TimeStampedModel


class MobileID(TimeStampedModel):
    """
    Mobile ID configuration bound to a barcode.
    """

    # foreign keys linked to the user
    model_user = models.ForeignKey("authn.Member", on_delete=models.CASCADE)
    
    # user barcode
    user_barcode = models.ForeignKey("mobileid.Barcode", on_delete=models.CASCADE)
    user_activate_barcode = models.ForeignKey("mobileid.Barcode", on_delete=models.CASCADE, related_name="user_activate_barcode")
    user_mobile_id_server = models.CharField(
        max_length=255,
        default="i2g.ucmerced.edu",
        verbose_name="user mobile id server",
    )

    class Meta:
        verbose_name = "Mobile ID"
        verbose_name_plural = "Mobile IDs"
        db_table = "authn_mobileid"

    def __str__(self):
        return f"MobileID for {self.model_user.username} ({self.user_mobile_id_server})"

