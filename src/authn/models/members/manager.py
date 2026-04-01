from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import BaseUserManager

from core.models.managers.base import ProjectControlQuerySet


class MemberManager(BaseUserManager):
    """Custom manager for Member without a username field.

    Integrates soft-delete filtering from ProjectControlManager.
    """

    use_in_migrations = True

    def get_queryset(self):
        return ProjectControlQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def _create_user(self, password=None, **extra_fields):
        user = self.model(**extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(password, **extra_fields)

    def create_superuser(self, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(password, **extra_fields)
