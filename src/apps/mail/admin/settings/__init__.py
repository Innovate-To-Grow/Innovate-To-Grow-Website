from .admin import get_mail_settings_urls as _notification_delivery_urls
from .rates import get_delivery_rate_urls


def get_mail_settings_urls():
    """Notification Delivery and Delivery Rates (both under Mail → Delivery Operations)."""
    return get_delivery_rate_urls() + _notification_delivery_urls()


__all__ = ["get_mail_settings_urls"]
