from django.db import models

from apps.core.models import ProjectControlModel


class LoginFailureWindow(ProjectControlModel):
    """Password sign-in failures counted for one identifier in one clock-aligned window.

    Written only by ``apps.authn.services.login_guard``. ``identifier_digest`` is a SECRET_KEY-salted HMAC of the
    normalised identifier (never the identifier itself), or the constant ``GLOBAL_DIGEST`` for the site-wide
    spray-detection counter. ``window_index`` is ``unix time // window length``; ``expires_at`` is the end of that
    window, after which the row is dead weight for ``purge_expired_failure_windows``. Increments are single
    ``UPDATE ... SET failure_count = failure_count + 1`` statements, so ``updated_at`` stays at the row's creation.
    """

    GLOBAL_DIGEST = "global"

    class Window(models.TextChoices):
        FIFTEEN_MINUTES = "15m", "15 minutes"
        ONE_DAY = "24h", "24 hours"
        GLOBAL_FIVE_MINUTES = "5m", "5 minutes (all identifiers)"

    identifier_digest = models.CharField(max_length=64)
    window = models.CharField(max_length=8, choices=Window.choices)
    window_index = models.BigIntegerField()
    failure_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["identifier_digest", "window", "window_index"],
                name="authn_login_failure_window_unique",
            ),
        ]
