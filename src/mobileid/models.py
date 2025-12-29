import uuid

from django.db import models


class Barcode(models.Model):
    """
    Physical/virtual barcode assigned to a member.
    """

    model_user = models.ForeignKey("authn.Member", on_delete=models.CASCADE)
    time_created = models.DateTimeField(
        auto_now_add=True, null=True, verbose_name="time created"
    )
    barcode_uuid = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, verbose_name="barcode uuid"
    )
    BARCODE_TYPE = [
        ("CatCard Barcode", "CatCardBarcode"),
        ("Identification", "Identification"),
    ]
    barcode_type = models.CharField(
        max_length=255, choices=BARCODE_TYPE, verbose_name="barcode type"
    )
    barcode = models.CharField(max_length=255, verbose_name="barcode")
    profile_img = models.TextField(
        null=True,
        blank=True,
        help_text="Base64 encoded PNG. No data-URL prefix",
    )
    profile_information_id = models.TextField(
        null=True,
        blank=True,
    )
    profile_name = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-time_created"]
        verbose_name = "Barcode"
        verbose_name_plural = "Barcodes"
        db_table = "authn_barcode"

    def __str__(self):
        return f"{self.get_barcode_type_display()} for {self.model_user.username}"

    @property
    def has_profile(self) -> bool:
        """
        Whether this barcode has any profile metadata attached.
        """
        return bool(self.profile_img or self.profile_information_id or self.profile_name)

    def get_profile_label(self) -> str:
        """
        Human-friendly label for display; fallback to UUID when not named.
        """
        return self.profile_name or str(self.barcode_uuid)


class MobileID(models.Model):
    """
    Mobile ID configuration bound to a barcode.
    """

    model_user = models.ForeignKey("authn.Member", on_delete=models.CASCADE)
    user_barcode = models.ForeignKey("mobileid.Barcode", on_delete=models.CASCADE)
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


class Transaction(models.Model):
    """
    Usage log tying members and barcodes.
    """

    model_user = models.ForeignKey("authn.Member", on_delete=models.CASCADE)
    barcode_used = models.ForeignKey("mobileid.Barcode", on_delete=models.CASCADE)
    time_used = models.DateTimeField(
        auto_now_add=True, null=True, verbose_name="time used"
    )

    class Meta:
        ordering = ["-time_used"]
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        db_table = "authn_transaction"

    def __str__(self):
        return f"{self.model_user.username} used {self.barcode_used} @ {self.time_used}"

