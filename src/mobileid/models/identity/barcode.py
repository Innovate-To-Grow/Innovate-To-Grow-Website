from django.db import models

from core.models import ProjectControlModel


class Barcode(ProjectControlModel):
    """
    Physical/virtual barcode assigned to a member.
    """

    # foreign key linked to the user
    model_user = models.ForeignKey("authn.Member", on_delete=models.CASCADE)

    BARCODE_TYPE = [
        ("DynamicBarcode", "DynamicBarcode"),
        ("Identification", "Identification"),
        ("EventOneTimePass", "EventOneTimePass"),
    ]
    barcode_type = models.CharField(max_length=255, choices=BARCODE_TYPE, verbose_name="barcode type")
    barcode = models.CharField(max_length=255, verbose_name="barcode")

    # barcode profile
    profile_name = models.TextField(
        null=True,
        blank=True,
    )
    profile_img = models.TextField(
        null=True,
        blank=True,
        help_text="Base64 encoded PNG. No data-URL prefix",
    )
    profile_information_id = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
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

    @property
    def barcode_uuid(self):
        """Return the barcode's UUID (alias for id from ProjectControlModel)."""
        return self.id

    def get_profile_label(self) -> str:
        """
        Human-friendly label for display; fallback to UUID when not named.
        """
        return self.profile_name or str(self.id)
