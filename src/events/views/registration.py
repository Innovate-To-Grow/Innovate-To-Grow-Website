"""
API views for event registration flow.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from notify.models import VerificationRequest
from notify.services import RateLimitError, VerificationError, issue_code, issue_link, verify_code

from ..models import EventRegistration, EventRegistrationAnswer
from ..serializers import (
    EventRegistrationRequestLinkSerializer,
    EventRegistrationSubmitSerializer,
    EventRegistrationVerifyOTPSerializer,
)
from ..services.registration import (
    EventRegistrationFlowError,
    build_registration_snapshot,
    get_live_event,
    get_registration_from_token,
    normalize_phone,
    resolve_member_by_email,
)


def _error_response(code: str, message: str, *, http_status: int):
    return Response({"error": message, "code": code}, status=http_status)


def _error_status_for_registration_flow(exc: EventRegistrationFlowError) -> int:
    if exc.code in {"no_live_event", "member_not_found", "event_not_found"}:
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_400_BAD_REQUEST


def _resolve_live_event_for_slug(event_slug: str | None):
    event = get_live_event()
    if event_slug and event.slug != event_slug:
        raise EventRegistrationFlowError(
            "event_not_found",
            f"No live event found for slug '{event_slug}'.",
        )
    return event


class EventRegistrationRequestLinkAPIView(APIView):
    """
    Send registration link to member email for current live event.
    """

    permission_classes = [AllowAny]

    def get(self, request, event_slug: str | None = None):
        try:
            event = _resolve_live_event_for_slug(event_slug)
        except EventRegistrationFlowError as exc:
            return _error_response(
                exc.code,
                exc.message,
                http_status=_error_status_for_registration_flow(exc),
            )

        return Response(
            {
                "status": "ready",
                "event_slug": event.slug,
                "event_name": event.event_name,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, event_slug: str | None = None):
        serializer = EventRegistrationRequestLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()

        try:
            event = _resolve_live_event_for_slug(event_slug)
        except EventRegistrationFlowError as exc:
            return _error_response(
                exc.code,
                exc.message,
                http_status=_error_status_for_registration_flow(exc),
            )

        member = resolve_member_by_email(email)
        if not member:
            return _error_response(
                "member_not_found",
                "No member account is associated with this email. Complete membership registration first.",
                http_status=status.HTTP_404_NOT_FOUND,
            )

        registration, _ = EventRegistration.objects.get_or_create(
            event=event,
            member=member,
            defaults={"source_email": email, "status": EventRegistration.STATUS_PENDING},
        )

        try:
            base_url = request.build_absolute_uri(f"/membership/event-registration/{event.slug}")
            verification, link = issue_link(
                channel=VerificationRequest.CHANNEL_EMAIL,
                target=email,
                purpose="event_registration_link",
                expires_in_minutes=60,
                max_attempts=5,
                rate_limit_per_hour=5,
                base_url=base_url,
                context={
                    "recipient_name": member.get_full_name() or member.username,
                    "event_name": event.event_name,
                },
            )
        except RateLimitError as exc:
            return _error_response("rate_limited", str(exc), http_status=status.HTTP_429_TOO_MANY_REQUESTS)

        registration.registration_token = verification.token
        registration.source_email = email
        registration.status = EventRegistration.STATUS_PENDING
        registration.save(update_fields=["registration_token", "source_email", "status", "updated_at"])

        return Response(
            {
                "status": "sent",
                "email": email,
                "event_slug": event.slug,
                "registration_token": verification.token if settings.DEBUG else None,
                "registration_link": link if settings.DEBUG else None,
            },
            status=status.HTTP_200_OK,
        )


class EventRegistrationFormAPIView(APIView):
    """
    Return registration form payload for a valid token.
    """

    permission_classes = [AllowAny]

    def get(self, request, event_slug: str | None = None, token: str | None = None):
        token = (token or request.query_params.get("token") or "").strip()
        if not token:
            return _error_response("invalid_token", "Token is required.", http_status=status.HTTP_400_BAD_REQUEST)

        try:
            context = get_registration_from_token(token, verify_token=True)
        except EventRegistrationFlowError as exc:
            return _error_response(
                exc.code,
                exc.message,
                http_status=_error_status_for_registration_flow(exc),
            )

        event = context.event
        if event_slug and event.slug != event_slug:
            return _error_response(
                "event_not_found",
                f"No live event found for slug '{event_slug}'.",
                http_status=status.HTTP_404_NOT_FOUND,
            )
        registration = context.registration
        member = context.member

        snapshot = registration.profile_snapshot or {}
        answers = [
            {
                "question_id": str(answer.question_id) if answer.question_id else None,
                "question_prompt": answer.question_prompt,
                "answer_text": answer.answer_text,
            }
            for answer in registration.answers.all().order_by("order", "id")
        ]

        questions = [
            {
                "id": str(question.id),
                "prompt": question.prompt,
                "order": question.order,
                "required": question.required,
            }
            for question in event.questions.filter(is_active=True).order_by("order", "id")
        ]
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
                "event_date": event.event_date.isoformat() if event.event_date else None,
                "event_time": event.event_time.isoformat() if event.event_time else None,
            },
            "member": {
                "member_uuid": str(member.member_uuid),
                "first_name": member.first_name or "",
                "last_name": member.last_name or "",
                "primary_email": member.email or "",
                "secondary_email": snapshot.get("secondary_email", ""),
            },
            "registration": {
                "status": registration.status,
                "ticket_option_id": str(registration.ticket_option_id) if registration.ticket_option_id else None,
                "ticket_label": registration.ticket_label,
                "primary_email_subscribed": registration.primary_email_subscribed,
                "secondary_email_subscribed": registration.secondary_email_subscribed,
                "phone_subscribed": registration.phone_subscribed,
                "phone_verified": registration.phone_verified,
                "phone_number": registration.otp_target_phone or snapshot.get("phone_number", ""),
                "answers": answers,
            },
            "schema": {
                "ticket_options": ticket_options,
                "questions": questions,
            },
        }

        return Response(payload, status=status.HTTP_200_OK)


class EventRegistrationSubmitAPIView(APIView):
    """
    Submit registration form payload. Starts OTP when needed.
    """

    permission_classes = [AllowAny]

    def post(self, request, event_slug: str | None = None, token: str | None = None):
        serializer_input = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if token and not serializer_input.get("token"):
            serializer_input["token"] = token

        serializer = EventRegistrationSubmitSerializer(data=serializer_input)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            context = get_registration_from_token(data["token"], verify_token=True)
        except EventRegistrationFlowError as exc:
            return _error_response(
                exc.code,
                exc.message,
                http_status=_error_status_for_registration_flow(exc),
            )

        event = context.event
        if event_slug and event.slug != event_slug:
            return _error_response(
                "event_not_found",
                f"No live event found for slug '{event_slug}'.",
                http_status=status.HTTP_404_NOT_FOUND,
            )
        member = context.member
        registration = context.registration

        provided_primary_email = data.get("primary_email")
        if provided_primary_email and provided_primary_email.strip().lower() != member.email.lower():
            return _error_response(
                "primary_email_locked",
                "Primary email cannot be changed in event registration flow.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            first_name = (data.get("first_name") or "").strip()
            last_name = (data.get("last_name") or "").strip()
            if first_name != member.first_name or last_name != member.last_name:
                member.first_name = first_name
                member.last_name = last_name
                member.save(update_fields=["first_name", "last_name"])

            ticket_option = None
            ticket_option_id = data.get("ticket_option_id")
            if ticket_option_id:
                ticket_option = event.ticket_options.filter(id=ticket_option_id, is_active=True).first()
                if not ticket_option:
                    return _error_response(
                        "invalid_ticket_option",
                        "Invalid or inactive ticket option.",
                        http_status=status.HTTP_400_BAD_REQUEST,
                    )

            secondary_email = (data.get("secondary_email") or "").strip().lower()
            phone_number = normalize_phone(data.get("phone_number", ""), data.get("phone_region", ""))
            answers_payload = data.get("answers", [])

            registration.ticket_option = ticket_option
            registration.ticket_label = (data.get("ticket_label") or (ticket_option.label if ticket_option else "")).strip()
            registration.source_email = member.email.lower()
            registration.primary_email_subscribed = bool(data.get("primary_email_subscribed", False))
            registration.secondary_email_subscribed = bool(data.get("secondary_email_subscribed", False) and secondary_email)
            registration.phone_subscribed = bool(data.get("phone_subscribed", False) and phone_number)

            # Save answers as full replace for deterministic behavior.
            registration.answers.all().delete()
            normalized_answers = []
            for index, answer_payload in enumerate(answers_payload):
                question = None
                question_id = answer_payload.get("question_id")
                if question_id:
                    question = event.questions.filter(id=question_id, is_active=True).first()
                prompt = (
                    question.prompt
                    if question
                    else (answer_payload.get("question_prompt") or "").strip()
                )
                if not prompt:
                    continue
                answer_text = (answer_payload.get("answer_text") or "").strip()
                EventRegistrationAnswer.objects.create(
                    registration=registration,
                    question=question,
                    question_prompt=prompt,
                    answer_text=answer_text,
                    order=index,
                )
                normalized_answers.append(
                    {
                        "question_id": str(question.id) if question else None,
                        "question_prompt": prompt,
                        "answer_text": answer_text,
                    }
                )

            registration.profile_snapshot = build_registration_snapshot(
                primary_email=member.email,
                secondary_email=secondary_email,
                phone_number=phone_number,
                answers=normalized_answers,
            )

            now = timezone.now()
            if registration.phone_subscribed and phone_number:
                try:
                    issue_code(
                        channel=VerificationRequest.CHANNEL_SMS,
                        target=phone_number,
                        purpose="event_phone_verification",
                        expires_in_minutes=10,
                        max_attempts=5,
                        rate_limit_per_hour=5,
                        context={
                            "event_name": event.event_name,
                        },
                    )
                except RateLimitError as exc:
                    return _error_response("rate_limited", str(exc), http_status=status.HTTP_429_TOO_MANY_REQUESTS)

                registration.status = EventRegistration.STATUS_OTP_PENDING
                registration.phone_verified = False
                registration.otp_target_phone = phone_number
                registration.otp_requested_at = now
                registration.submitted_at = now
                registration.save()

                return Response(
                    {
                        "status": registration.status,
                        "otp_required": True,
                    },
                    status=status.HTTP_200_OK,
                )

            registration.status = EventRegistration.STATUS_COMPLETED
            registration.phone_verified = False
            registration.otp_target_phone = phone_number
            registration.otp_requested_at = None
            registration.submitted_at = now
            registration.save()

            return Response(
                {
                    "status": registration.status,
                    "otp_required": False,
                },
                status=status.HTTP_200_OK,
            )


class EventRegistrationVerifyOTPAPIView(APIView):
    """
    Verify OTP code for pending event registration.
    """

    permission_classes = [AllowAny]

    def post(self, request, event_slug: str | None = None, token: str | None = None):
        serializer_input = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if token and not serializer_input.get("token"):
            serializer_input["token"] = token

        serializer = EventRegistrationVerifyOTPSerializer(data=serializer_input)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            context = get_registration_from_token(data["token"], verify_token=True)
        except EventRegistrationFlowError as exc:
            return _error_response(
                exc.code,
                exc.message,
                http_status=_error_status_for_registration_flow(exc),
            )

        if event_slug and context.event.slug != event_slug:
            return _error_response(
                "event_not_found",
                f"No live event found for slug '{event_slug}'.",
                http_status=status.HTTP_404_NOT_FOUND,
            )
        registration = context.registration
        if not registration.otp_target_phone:
            return _error_response(
                "otp_not_requested",
                "No OTP verification is pending for this registration.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            verify_code(
                channel=VerificationRequest.CHANNEL_SMS,
                target=registration.otp_target_phone,
                submitted_code=data["code"],
                purpose="event_phone_verification",
            )
        except VerificationError as exc:
            return _error_response("invalid_otp", str(exc), http_status=status.HTTP_400_BAD_REQUEST)

        registration.phone_verified = True
        registration.status = EventRegistration.STATUS_COMPLETED
        registration.otp_verified_at = timezone.now()
        if registration.submitted_at is None:
            registration.submitted_at = timezone.now()
        registration.save(update_fields=["phone_verified", "status", "otp_verified_at", "submitted_at", "updated_at"])

        return Response(
            {
                "status": registration.status,
                "phone_verified": registration.phone_verified,
            },
            status=status.HTTP_200_OK,
        )


class EventRegistrationStatusAPIView(APIView):
    """
    Read current status for registration token.
    """

    permission_classes = [AllowAny]

    def get(self, request, event_slug: str | None = None, token: str | None = None):
        token = (token or request.query_params.get("token") or "").strip()
        if not token:
            return _error_response("invalid_token", "Token is required.", http_status=status.HTTP_400_BAD_REQUEST)

        try:
            context = get_registration_from_token(token, verify_token=False)
        except EventRegistrationFlowError as exc:
            return _error_response(
                exc.code,
                exc.message,
                http_status=_error_status_for_registration_flow(exc),
            )

        if event_slug and context.event.slug != event_slug:
            return _error_response(
                "event_not_found",
                f"No live event found for slug '{event_slug}'.",
                http_status=status.HTTP_404_NOT_FOUND,
            )

        registration = context.registration
        return Response(
            {
                "status": registration.status,
                "phone_verified": registration.phone_verified,
                "submitted_at": registration.submitted_at.isoformat() if registration.submitted_at else None,
                "event_slug": context.event.slug,
                "event_name": context.event.event_name,
            },
            status=status.HTTP_200_OK,
        )


class MembershipEventRegistrationAPIView(APIView):
    """
    Legacy-compatible endpoint:
    - GET  /membership/event-registration/<event_slug>/<token>
    - POST /membership/event-registration/<event_slug>/<token>
    """

    permission_classes = [AllowAny]

    def get(self, request, event_slug: str, token: str):
        return EventRegistrationFormAPIView().get(
            request,
            event_slug=event_slug,
            token=token,
        )

    def post(self, request, event_slug: str, token: str):
        return EventRegistrationSubmitAPIView().post(
            request,
            event_slug=event_slug,
            token=token,
        )
