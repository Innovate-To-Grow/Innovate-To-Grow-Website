"""The ticket page's own views (adding an internal note, replying to the requester, downloading an attachment) and
the context its reply form and field helpers need.

``admin_view`` only requires a staff login, so each view checks the Helpdesk grant itself (403 without it), and an
attachment must belong to the ticket in its URL. A download is always ``Content-Disposition: attachment`` with
``X-Content-Type-Options: nosniff``, served as ``application/octet-stream`` unless it is a raster image, and never
cached; an archive is offered only after a warning page, and a file whose content is not stored is a 404 that says
why. A refused reply comes back with what was typed (kept in the session for the next view of the page).
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST

from apps.core.utils.access import user_can_access_app

from ...models import AssignmentGroup, HelpdeskSettings, ResponseTemplate, Ticket, TicketAttachment
from ...services import outbound, tickets
from ...services.ingest.reading import attachments as files
from ...services.sla.priority import priority_for

# The statuses the reply form offers, set on the ticket when the reply is queued; "" keeps the current one.
REPLY_STATUS_CHOICES = (
    (Ticket.Status.PENDING_CUSTOMER, "On hold – awaiting requester"),
    ("", "Keep the current status"),
    (Ticket.Status.OPEN, "In progress"),
)
DONE = (Ticket.Status.RESOLVED, Ticket.Status.CLOSED)


def require_helpdesk_access(request) -> None:
    if not user_can_access_app(request.user, "helpdesk"):
        raise PermissionDenied


def _ticket_url(ticket: Ticket) -> str:
    return reverse("admin:helpdesk_ticket_change", args=[ticket.pk])


def _draft_key(ticket: Ticket) -> str:
    return f"helpdesk_reply_draft:{ticket.pk}"


@require_POST
def note_view(request, pk):
    require_helpdesk_access(request)
    ticket = get_object_or_404(Ticket, pk=pk)
    body = str(request.POST.get("body") or "").replace("\r\n", "\n").strip()
    if ticket.status == Ticket.Status.MERGED:
        target = ticket.merged_into
        where = f" into {target.display_number}: add the note there" if target is not None else ""
        messages.error(request, f"{ticket.display_number} was merged{where}. Nothing was added.")
        return HttpResponseRedirect(_ticket_url(target or ticket))
    if not body:
        messages.error(request, "Write the note before adding it.")
    elif len(body) > tickets.NOTE_MAX_CHARS:
        messages.error(request, f"A note can be at most {tickets.NOTE_MAX_CHARS:,} characters.")
    else:
        tickets.add_note(ticket, actor=request.user, body=body)
        messages.success(request, "Internal note added. Notes are never sent to anyone.")
    return HttpResponseRedirect(f"{_ticket_url(ticket)}#helpdesk-note")


@require_POST
def reply_view(request, pk):
    """Queue a reply to the requester (only while shadow mode is off; ``outbound.queue_reply`` decides and says why
    not). The status chosen with it must be one the form offers."""
    require_helpdesk_access(request)
    ticket = get_object_or_404(Ticket, pk=pk)
    status = str(request.POST.get("status") or "")
    if status not in {value for value, _label in REPLY_STATUS_CHOICES}:
        status = ""
    body, cc = str(request.POST.get("body") or ""), str(request.POST.get("cc") or "")
    try:
        outbound.queue_reply(ticket, actor=request.user, body=body, cc=cc, status=status)
    except outbound.ReplyRefused as refused:
        messages.error(request, f"The reply was not sent: {refused}")
        request.session[_draft_key(ticket)] = {"body": body, "cc": cc, "status": status, "error": str(refused)}
        return HttpResponseRedirect(f"{_ticket_url(ticket)}#helpdesk-reply")
    messages.success(request, f"Reply queued to {ticket.requester_email}; its delivery shows on the timeline.")
    return HttpResponseRedirect(f"{_ticket_url(ticket)}#helpdesk-timeline")


def reply_context(request, ticket: Ticket, settings: HelpdeskSettings) -> dict:
    """The reply form: why it is not offered, or its fields, templates (the ticket's category first, each already
    filled in for the ticket) and what a refused reply left typed."""
    draft = request.session.pop(_draft_key(ticket), None) if request.method == "GET" else None
    refusal = outbound.can_reply(ticket, settings)
    if refusal:
        # A reply refused because sending stopped meanwhile: its text stays on the page to copy.
        draft = draft or {}
        return {
            "helpdesk_reply_refusal": refusal,
            "helpdesk_reply_body": draft.get("body", ""),
            "helpdesk_reply_cc": draft.get("cc", ""),
        }
    same_category = Case(
        When(Q(category_id=ticket.category_id) & Q(category__isnull=False), then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    templates = list(
        ResponseTemplate.objects.filter(is_active=True)
        .select_related("category")
        .annotate(same_category=same_category)
        .order_by("same_category", "order", "name")
    )
    filled = [
        {
            "id": str(item.pk),
            "name": item.name,
            "category": item.category.name if item.category_id else "",
            "body": outbound.fill(item.body, ticket, agent=request.user),
        }
        for item in templates
    ]
    chosen = next((item for item in filled if item["id"] == str(request.GET.get("template") or "")), None)
    requester = ticket.requester_email.lower()
    default_status = "" if ticket.status in DONE else Ticket.Status.PENDING_CUSTOMER
    return {
        "helpdesk_reply_url": reverse("admin:helpdesk_ticket_reply", args=[ticket.pk]),
        "helpdesk_reply_to": ticket.requester_email,
        "helpdesk_reply_subject": outbound.reply_subject(ticket),
        "helpdesk_reply_cc_suggestions": [item for item in ticket.participants or [] if item.lower() != requester],
        "helpdesk_reply_templates": filled,
        "helpdesk_reply_template": chosen,
        "helpdesk_reply_body": (draft or {}).get("body") or (chosen["body"] if chosen else ""),
        "helpdesk_reply_cc": (draft or {}).get("cc", ""),
        "helpdesk_reply_error": (draft or {}).get("error", ""),
        "helpdesk_reply_statuses": REPLY_STATUS_CHOICES,
        "helpdesk_reply_status": (draft or {}).get("status", default_status),
        "helpdesk_reply_max": outbound.REPLY_MAX_CHARS,
    }


def form_helpers(request, ticket: Ticket) -> dict:
    """What the ticket form's script needs: each group's members who may hold its tickets (the Assigned to list
    follows the group), the priority each impact and urgency give, who "Assign to me" means, and whether the page
    shows the saved values (a GET) rather than a refused save's input."""
    groups = {
        str(group.pk): [str(member.pk) for member in tickets.eligible_members(group)]
        for group in AssignmentGroup.objects.prefetch_related("members")
    }
    labels = dict(Ticket.Priority.choices)
    priorities = {f"{i}-{u}": str(labels[priority_for(i, u)]) for i in (1, 2, 3) for u in (1, 2, 3)}
    data = {"groups": groups, "priorities": priorities, "me": str(request.user.pk), "fresh": request.method == "GET"}
    return {"helpdesk_form_data": data}


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
        return TemplateResponse(request, "admin/helpdesk/ticket/attachment_warning.html", context)
    response = HttpResponse(bytes(attachment.content), content_type=files.download_content_type(attachment))
    response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=attachment.filename)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response
