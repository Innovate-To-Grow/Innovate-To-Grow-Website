"""Allowed redirect destinations for campaign magic-login links."""

from cms.app_routes import APP_ROUTES
from cms.models import CMSPage

DEFAULT_LOGIN_REDIRECT_PATH = "/account"


def is_safe_internal_redirect_path(path: str | None) -> bool:
    value = (path or "").strip()
    return bool(value) and value.startswith("/") and not value.startswith("//")


def get_magic_login_redirect_path(campaign) -> str:
    candidate = getattr(campaign, "login_redirect_path", None) if campaign is not None else None
    return candidate.strip() if is_safe_internal_redirect_path(candidate) else DEFAULT_LOGIN_REDIRECT_PATH


def get_login_redirect_choices(*, current_path: str | None = None) -> list[tuple[str, str]]:
    choices = [(DEFAULT_LOGIN_REDIRECT_PATH, f"Account ({DEFAULT_LOGIN_REDIRECT_PATH})")]
    seen = {DEFAULT_LOGIN_REDIRECT_PATH}

    for route in APP_ROUTES:
        path = route.get("url", "").strip()
        if not is_safe_internal_redirect_path(path) or path in seen:
            continue
        title = route.get("title", path)
        choices.append((path, f"{title} ({path})"))
        seen.add(path)

    cms_pages = CMSPage.objects.filter(status="published").order_by("title").values("route", "title")
    for page in cms_pages:
        path = page["route"]
        if not is_safe_internal_redirect_path(path) or path in seen:
            continue
        choices.append((path, f"{page['title']} ({path})"))
        seen.add(path)

    if current_path and is_safe_internal_redirect_path(current_path) and current_path not in seen:
        choices.append((current_path, f"Current selection ({current_path})"))

    return choices
