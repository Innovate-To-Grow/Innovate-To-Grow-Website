"""
Server-rendered membership pages for event registration.

These pages intentionally keep a visual flow close to the legacy Flask
membership pages while using the new DB-primary registration APIs.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404
from django.shortcuts import render
from django.views import View

from ..models import EventRegistration
from ..services.registration import (
    EventRegistrationFlowError,
    get_live_event,
    get_registration_from_token,
    resolve_member_by_email,
)


def _render_no_live_event(request):
    return render(request, "events/membership/no_live_event.html", status=200)


def _load_live_event(event_slug: str | None):
    event = get_live_event()
    if event_slug and event.slug != event_slug:
        raise Http404(f"No live event found for slug '{event_slug}'.")
    return event


class MembershipEventsPageView(View):
    """
    Legacy-style event email entry page.
    """

    template_name = "events/membership/events_entry.html"

    def _base_context(self, event):
        return {
            "event": event,
            "page_title": f"{event.event_name} Registration",
            "page_subtitle": "Enter your email address for a registration link.",
        }

    def get(self, request, event_slug: str | None = None):
        try:
            event = _load_live_event(event_slug)
        except EventRegistrationFlowError:
            return _render_no_live_event(request)

        context = self._base_context(event)
        return render(request, self.template_name, context, status=200)

    def post(self, request, event_slug: str | None = None):
        try:
            event = _load_live_event(event_slug)
        except EventRegistrationFlowError:
            return _render_no_live_event(request)

        context = self._base_context(event)
        email = (request.POST.get("email") or "").strip().lower()
        context["email"] = email

        try:
            validate_email(email)
        except ValidationError:
            context["error_message"] = "Please enter a valid email address."
            return render(request, self.template_name, context, status=400)

        member = resolve_member_by_email(email)
        if not member:
            context["error_message"] = (
                "No member account is associated with this email. Please complete membership registration first."
            )
            return render(request, self.template_name, context, status=404)

        registration, _ = EventRegistration.objects.get_or_create(
            event=event,
            member=member,
            defaults={"source_email": email, "status": EventRegistration.STATUS_PENDING},
        )

        token = uuid.uuid4().hex
        registration.registration_token = token
        registration.source_email = email
        registration.status = EventRegistration.STATUS_PENDING
        registration.save(update_fields=["registration_token", "source_email", "status", "updated_at"])

        link = request.build_absolute_uri(f"/membership/event-registration/{event.slug}/{token}")
        context["success_message"] = "Instructions sent. Please check your inbox for the event registration link."
        context["debug_registration_link"] = link
        return render(request, self.template_name, context, status=200)


class MembershipEventRegistrationPageView(View):
    """
    Legacy-style event registration page.
    """

    template_name = "events/membership/event_registration.html"

    def get(self, request, event_slug: str, token: str):
        try:
            context = get_registration_from_token(token)
        except EventRegistrationFlowError as exc:
            return render(
                request,
                self.template_name,
                {"error_message": exc.message, "event_slug": event_slug, "token": token},
                status=400,
            )

        event = context.event
        if event.slug != event_slug:
            raise Http404(f"No live event found for slug '{event_slug}'.")

        registration = context.registration
        member = context.member

        snapshot = registration.profile_snapshot or {}
        stored_answers = {
            str(answer.question_id): answer.answer_text
            for answer in registration.answers.all().order_by("order", "id")
            if answer.question_id
        }
        stored_prompt_answers = {
            answer.question_prompt: answer.answer_text
            for answer in registration.answers.all().order_by("order", "id")
            if answer.question_prompt
        }

        questions = []
        for question in event.questions.filter(is_active=True).order_by("order", "id"):
            answer_text = stored_answers.get(str(question.id), stored_prompt_answers.get(question.prompt, ""))
            questions.append(
                {
                    "id": str(question.id),
                    "prompt": question.prompt,
                    "order": question.order,
                    "required": question.required,
                    "answer_text": answer_text,
                }
            )

        ticket_options = [
            {
                "id": str(ticket.id),
                "label": ticket.label,
                "order": ticket.order,
            }
            for ticket in event.ticket_options.filter(is_active=True).order_by("order", "id")
        ]

        payload = {
            "event": {
                "event_uuid": str(event.event_uuid),
                "slug": event.slug,
                "event_name": event.event_name,
                "event_date": event.event_date.isoformat() if event.event_date else "",
                "event_time": event.event_time.isoformat() if event.event_time else "",
            },
            "member": {
                "first_name": member.first_name or "",
                "last_name": member.last_name or "",
                "primary_email": member.email or "",
                "secondary_email": snapshot.get("secondary_email", ""),
            },
            "registration": {
                "ticket_option_id": str(registration.ticket_option_id) if registration.ticket_option_id else "",
                "ticket_label": registration.ticket_label or "",
                "primary_email_subscribed": registration.primary_email_subscribed,
                "secondary_email_subscribed": registration.secondary_email_subscribed,
                "phone_subscribed": registration.phone_subscribed,
                "phone_number": registration.otp_target_phone or snapshot.get("phone_number", ""),
            },
            "schema": {
                "ticket_options": ticket_options,
                "questions": questions,
            },
        }

        return render(
            request,
            self.template_name,
            {
                "payload": payload,
                "event": event,
                "event_slug": event_slug,
                "token": token,
            },
            status=200,
        )
