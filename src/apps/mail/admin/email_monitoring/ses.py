"""Mail → Delivery Operations → Email Monitoring → Amazon SES: Amazon SES's own counts (AWS CloudWatch) and the SES
account suppression list. This tab is what the Delivery Dashboard was, and this module also answers that page's old
addresses.

Like every Email Monitoring view it requires the Mail app (``admin_view`` only checks ``is_staff``). The page and its
JSON read AWS when they are requested, as the Delivery Dashboard did; the other tabs never call AWS.

- ``/admin/mail/delivery-dashboard/`` redirects here with its query string (``?days=``): temporary (302), so the old
  path stays free and nothing caches it. It only ever answered GET.
- ``/admin/mail/delivery-dashboard/data/`` still answers, with the same JSON as ``ses/data/``, so a script that reads
  it (with or without following redirects) keeps working.
"""

from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.views.generic import RedirectView

from apps.mail.services.campaign.dashboard import get_delivery_dashboard_data
from apps.mail.services.email_monitoring import ses

from .views import TEMPLATES, _context, require_mail_access


def ses_view(request):
    require_mail_access(request)
    days = ses.window_days(request.GET)
    context = _context(request, "Amazon SES Delivery", None, "ses")
    context.update(ses.tab(get_delivery_dashboard_data(days=days), days))
    return TemplateResponse(request, f"{TEMPLATES}/ses.html", context)


def ses_data_view(request):
    """The dashboard payload as JSON (``?days=``), unchanged since the Delivery Dashboard."""
    require_mail_access(request)
    return JsonResponse(get_delivery_dashboard_data(days=ses.window_days(request.GET)))


class DeliveryDashboardRedirect(RedirectView):
    """The old Delivery Dashboard page → the Amazon SES tab, keeping the query string."""

    pattern_name = "admin:mail_email_monitoring_ses"
    permanent = False
    query_string = True
    http_method_names = ["get", "head"]
