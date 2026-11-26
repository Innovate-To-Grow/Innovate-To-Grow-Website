from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import ProjectControlModel
from apps.core.utils.access import user_is_admin

from .manager import MemberManager


class Member(AbstractUser, ProjectControlModel):
    username = None

    USERNAME_FIELD = "id"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = MemberManager()

    # Set only on members created by the self-service registration flows (email-code
    # and password /register) and cleared the first time the member becomes active.
    # It is what tells an unfinished signup apart from an account an admin
    # deactivated: only a pending registration may be activated by proving email
    # ownership. Fail-closed — any other inactive member is never self-activatable.
    registration_pending = models.BooleanField(
        default=False,
        db_default=False,
        editable=False,
        help_text="Self-service registration not yet completed. Cleared once the member is first activated.",
        verbose_name="Registration pending",
    )

    # Two kinds of account: Admins (``is_staff``) and regular members. Every Admin has every permission, so
    # ``is_superuser`` is only a mirror of ``is_staff`` kept for Django's own machinery; the permission methods below
    # answer from the Admin test, so a row whose mirror is stale (written by a bulk update) is still judged right.
    def has_perm(self, perm, obj=None):
        return user_is_admin(self)

    def has_perms(self, perm_list, obj=None):
        return user_is_admin(self)

    def has_module_perms(self, app_label):
        return user_is_admin(self)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        extra = set()
        # Activation by any path (registration, admin form, invitation, import) ends the
        # pending state, so a later deactivation can't be undone through self-service.
        if self.is_active and self.registration_pending:
            self.registration_pending = False
            extra.add("registration_pending")
        # A deactivated account is never an Admin, so reactivating it later (an import, the assistant, an Admin's
        # bulk action) never brings back a full Admin unasked: Admin access is granted again on the member's page.
        # That includes a row an older release deactivated without removing Admin (``from_db`` notes it).
        # Writing ``is_active`` writes the demotion too; it only ever removes access, so it is safe from a partial load.
        stale = getattr(self, "_stored_inactive_admin", False)
        if self.is_staff and (not self.is_active or stale):
            self.is_staff = False
            if update_fields is not None and ("is_active" in update_fields or stale):
                extra.update({"is_staff", "is_superuser"})
        # ``is_superuser`` follows ``is_staff``. A partial save writes the mirror only when it writes ``is_staff``,
        # so saving an unrelated column never writes a value derived from a stale in-memory ``is_staff``.
        if self.is_superuser != self.is_staff:
            self.is_superuser = self.is_staff
            if update_fields is not None and "is_staff" in update_fields:
                extra.add("is_superuser")
        if update_fields is not None and extra:
            kwargs["update_fields"] = {*update_fields, *extra}
        super().save(*args, **kwargs)
        self._stored_inactive_admin = False

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        stored = instance.__dict__  # loaded columns only; a deferred one is absent
        instance._stored_inactive_admin = not stored.get("is_active", True) and bool(stored.get("is_staff"))
        return instance

    def get_username(self):
        """Return UUID as a string so templates and admin can handle it."""
        return str(self.id)

    def __str__(self):
        return self.get_full_name() or self.get_primary_email() or str(self.id)

    # add field for user models
    middle_name = models.CharField(max_length=255, null=True, blank=True, help_text="Middle Name")

    @property
    def member_uuid(self):
        """Return the member's UUID (alias for id from ProjectControlModel)."""
        return self.id

    @property
    def has_required_name_fields(self) -> bool:
        """Return whether the member has the required first and last name fields."""
        return bool((self.first_name or "").strip() and (self.last_name or "").strip())

    @property
    def requires_profile_completion(self) -> bool:
        """Return whether the member must complete their profile before continuing."""
        return not self.has_required_name_fields

    # organization
    organization = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Organization or company the member belongs to",
        verbose_name="Organization",
    )

    # job title or position
    title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Job title or position within the organization",
        verbose_name="Title",
    )

    # profile image (base64 encoded)
    profile_image = models.TextField(
        null=True,
        blank=True,
        help_text="Profile image, base64-encoded.",
        verbose_name="Profile Image",
    )

    # get full name including middle name
    def get_full_name(self):
        """
        Return the first_name plus the middle_name plus the last_name, with a space in between.
        """
        full_name = self.first_name
        if self.middle_name:
            full_name += f" {self.middle_name}"
        if self.last_name:
            full_name += f" {self.last_name}"
        return full_name.strip()

    def _primary_contact_from_prefetch(self):
        """Return the primary ContactEmail from the prefetch cache, or None if not prefetched."""
        cache = getattr(self, "_prefetched_objects_cache", None)
        if not cache or "contact_emails" not in cache:
            return None
        primaries = [c for c in cache["contact_emails"] if c.email_type == "primary"]
        if not primaries:
            return None
        primaries.sort(key=lambda c: c.created_at)
        return primaries[0]

    def get_primary_email(self) -> str:
        """Return the primary ContactEmail address, or empty string."""
        prefetched = self._primary_contact_from_prefetch()
        if prefetched is not None:
            return prefetched.email_address
        contact = self.contact_emails.filter(email_type="primary").order_by("created_at").first()
        return contact.email_address if contact else ""

    def get_primary_contact_email(self):
        """Return the primary ContactEmail object, or None."""
        prefetched = self._primary_contact_from_prefetch()
        if prefetched is not None:
            return prefetched
        return self.contact_emails.filter(email_type="primary").order_by("created_at").first()

    def _primary_phone_from_prefetch(self):
        """Return the primary ContactPhone from the prefetch cache, or None if not prefetched.

        Mirrors :meth:`_primary_contact_from_prefetch`: verified phones sort first
        (``-verified``), then earliest ``created_at``.
        """
        cache = getattr(self, "_prefetched_objects_cache", None)
        if not cache or "contact_phones" not in cache:
            return None
        phones = list(cache["contact_phones"])
        if not phones:
            return None
        phones.sort(key=lambda p: (-p.verified, p.created_at))
        return phones[0]

    def get_primary_contact_phone(self):
        """Return the member's primary ContactPhone, or None.

        ContactPhone has no ``phone_type`` (unlike ContactEmail), so pick
        deterministically: verified phones sort first (``-verified``), then the
        earliest within that group — i.e. the earliest verified phone, else the
        earliest phone overall. When ``contact_phones`` is prefetched the result
        is computed in-process with zero extra queries.
        """
        prefetched = self._primary_phone_from_prefetch()
        if prefetched is not None:
            return prefetched
        return self.contact_phones.order_by("-verified", "created_at").first()

    def get_primary_phone(self) -> str:
        """Return the member's primary phone (``get_primary_contact_phone``) in E.164, or empty string."""
        contact = self.get_primary_contact_phone()
        return contact.to_e164() if contact else ""
