"""The ticket page's own views: adding an internal note, and downloading an attachment.

``admin_view`` only requires a staff login, so each view checks the Helpdesk grant itself (403 without it), and an
attachment must belong to the ticket in its URL. A download is always ``Content-Disposition: attachment`` with
``X-Content-Type-Options: nosniff``, served as ``application/octet-stream`` unless it is a raster image, and never
cached; an archive is offered only after a warning page, and a file whose content is not stored is a 404 that says
why.
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST

from apps.core.utils.access import user_can_access_app

from ..models import HelpdeskSettings, Ticket, TicketAttachment
from ..services import tickets
from ..services.ingest import attachments as files


def require_helpdesk_access(request) -> None:
    if not user_can_access_app(request.user, "helpdesk"):
        raise PermissionDenied


def _ticket_url(ticket: Ticket) -> str:
    return reverse("admin:helpdesk_ticket_change", args=[ticket.pk])


@require_POST
def note_view(request, pk):
    require_helpdesk_access(request)
    ticket = get_object_or_404(Ticket, pk=pk)
    body = str(request.POST.get("body") or "").strip()
    if not body:
        messages.error(request, "Write the note before adding it.")
    elif len(body) > tickets.NOTE_MAX_CHARS:
        messages.error(request, f"A note can be at most {tickets.NOTE_MAX_CHARS:,} characters.")
    else:
        tickets.add_note(ticket, actor=request.user, body=body)
        messages.success(request, "Internal note added. Notes are never sent to anyone.")
    return HttpResponseRedirect(f"{_ticket_url(ticket)}#helpdesk-note")


@require_GET
def attachment_view(request, pk, attachment_pk):
    require_helpdesk_access(request)
    ticket = get_object_or_404(Ticket, pk=pk)
    attachment = get_object_or_404(TicketAttachment.objects.select_related("message"), pk=attachment_pk)
    if attachment.message.ticket_id != ticket.pk:
        raise Http404("No such attachment on this ticket.")
    if attachment.content is None:
        raise Http404(attachment.not_stored_reason or "This file is not stored.")
    settings = HelpdeskSettings.load()
    if files.needs_warning(attachment, settings) and request.GET.get("confirm") != "1":
        context = {
            **admin.site.each_context(request),
            "title": "Download an archive?",
            "ticket": ticket,
            "attachment": attachment,
            "download_url": f"{request.path}?confirm=1",
            "back_url": _ticket_url(ticket),
        }
        return TemplateResponse(request, "admin/helpdesk/attachment_warning.html", context)
    response = HttpResponse(bytes(attachment.content), content_type=files.download_content_type(attachment))
    response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=attachment.filename)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response
