import logging
import re
from hashlib import sha256

from django.core.cache import cache
from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.models import ContactPhone
from authn.services.contacts.contact_phones import normalize_to_national
from event.models import Event, EventRegistration, Question, Ticket
from event.serializers import (
    EventRegistrationCreateSerializer,
    build_event_registration_option_payload,
    build_registration_payload,
)
from event.services.registration_sheet_sync import schedule_registration_sync
from event.services.sync_registration_email import sync_secondary_email_to_account
from event.services.sync_registration_to_account import sync_name_to_account, sync_phone_to_account

logger = logging.getLogger(__name__)

_PHONE_VERIFICATION_TTL = 900


def _normalize_phone(phone: str, region: str) -> str:
    phone = phone.strip()
    if phone and not phone.startswith("+"):
        country_code = region.split("-")[0] if "-" in region else region
        phone = f"+{country_code}{phone}"
    return phone


_DIGITS_ONLY = re.compile(r"^\d+$")


def _validate_phone_digits(phone: str, region: str) -> str | None:
    """Validate phone digits. Accepts raw national digits or E.164 (+CC...) format."""
    digits = phone.strip()
    if not digits:
        return None

    # If already in E.164 format (+CC...), strip the prefix to get national digits.
    cc = region.split("-")[0] if "-" in region else region
    if digits.startswith("+"):
        digits = digits[1:]  # remove "+"
        if not _DIGITS_ONLY.match(digits):
            return "Phone number must contain only digits."
        if digits.startswith(cc):
            digits = digits[len(cc) :]
        # After stripping, fall through to national-length checks
    elif not _DIGITS_ONLY.match(digits):
        return "Phone number must contain only digits."

    if not digits:
        return "Phone number is too short (minimum 4 digits)."
    if cc == "1":
        if len(digits) != 10:
            return "US/Canada phone numbers must be exactly 10 digits."
        return None
    if cc == "86":
        if len(digits) != 11:
            return "China phone numbers must be exactly 11 digits."
        return None
    if len(digits) < 4:
        return "Phone number is too short (minimum 4 digits)."
    if len(digits) > 15:
        return "Phone number is too long (maximum 15 digits)."
    return None


def _phone_verification_cache_key(user, phone: str) -> str:
    phone_digest = sha256(phone.encode("utf-8")).hexdigest()
    return f"event:phone-verified:{user.pk}:{phone_digest}"


def _clear_phone_verification(user, phone: str) -> None:
    cache.delete(_phone_verification_cache_key(user, phone))


def _mark_phone_verified(user, phone: str) -> None:
    cache.set(_phone_verification_cache_key(user, phone), True, timeout=_PHONE_VERIFICATION_TTL)


def _consume_phone_verification(user, phone: str) -> bool:
    cache_key = _phone_verification_cache_key(user, phone)
    verified = cache.get(cache_key) is True
    if verified:
        cache.delete(cache_key)
    return verified


class EventRegistrationOptionsView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic,PyProtectedMember
    def get(self, request):
        event = (
            Event.objects.filter(is_live=True)
            .prefetch_related("questions")
            .prefetch_related(
                "tickets",
            )
            .first()
        )
        if event is None:
            return Response({"detail": "No live event available."}, status=status.HTTP_404_NOT_FOUND)

        registration = None
        if request.user.is_authenticated:
            registration = (
                EventRegistration.objects.filter(member=request.user, event=event)
                .select_related("event", "ticket")
                .first()
            )

        return Response(build_event_registration_option_payload(event, registration=registration, request=request))


class EventRegistrationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = EventRegistrationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            event = Event.objects.get(slug=data["event_slug"], is_live=True)
        except Event.DoesNotExist:
            return Response(
                {"detail": "Event not found or not currently accepting registrations."},
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = (
            EventRegistration.objects.filter(member=request.user, event=event).select_related("event", "ticket").first()
        )
        if existing:
            return Response(
                {
                    "detail": "You are already registered for this event.",
                    "registration": build_registration_payload(existing, request=request),
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            ticket = Ticket.objects.get(pk=data["ticket_id"], event=event)
        except Ticket.DoesNotExist:
            return Response({"detail": "Invalid ticket for this event."}, status=status.HTTP_400_BAD_REQUEST)

        questions = {str(q.pk): q for q in Question.objects.filter(event=event)}
        required_ids = {qid for qid, q in questions.items() if q.is_required}
        answers = data.get("answers", [])
        answered_map = {str(a["question_id"]): a["answer"] for a in answers}

        for req_id in required_ids:
            if not answered_map.get(req_id, "").strip():
                q_text = questions[req_id].text
                return Response({"detail": f'Answer required for: "{q_text}"'}, status=status.HTTP_400_BAD_REQUEST)

        question_answers = []
        for a in answers:
            qid = str(a["question_id"])
            if qid not in questions:
                return Response(
                    {"detail": "One of your answers references an invalid question. Please reload and try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            question_answers.append(
                {
                    "question_id": qid,
                    "question_text": questions[qid].text,
                    "answer": a["answer"],
                }
            )

        try:
            create_kwargs = {
                "member": request.user,
                "event": event,
                "ticket": ticket,
                "question_answers": question_answers,
            }
            if data.get("attendee_first_name"):
                create_kwargs["attendee_first_name"] = data["attendee_first_name"]
            if data.get("attendee_last_name"):
                create_kwargs["attendee_last_name"] = data["attendee_last_name"]
            if data.get("attendee_organization"):
                create_kwargs["attendee_organization"] = data["attendee_organization"]
            if data.get("attendee_secondary_email") and event.allow_secondary_email:
                create_kwargs["attendee_secondary_email"] = data["attendee_secondary_email"]
            phone_verified_inline = False
            phone_region = data.get("attendee_phone_region", "1-US")
            if data.get("attendee_phone") and event.collect_phone:
                phone_error = _validate_phone_digits(data["attendee_phone"], phone_region)
                if phone_error:
                    return Response({"detail": phone_error}, status=status.HTTP_400_BAD_REQUEST)
                phone = _normalize_phone(data["attendee_phone"], phone_region)
                create_kwargs["attendee_phone"] = phone
                if event.verify_phone:
                    national_digits = normalize_to_national(phone, phone_region)
                    phone_verified_inline = (
                        _consume_phone_verification(request.user, phone)
                        or ContactPhone.objects.filter(
                            member=request.user,
                            phone_number=national_digits,
                            verified=True,
                        ).exists()
                    )
                    if not phone_verified_inline:
                        return Response(
                            {"detail": "Please verify your phone number before completing registration."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    create_kwargs["phone_verified"] = True
            elif event.verify_phone:
                return Response(
                    {"detail": "A verified phone number is required for this event."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            registration = EventRegistration.objects.create(**create_kwargs)
        except IntegrityError:
            existing = (
                EventRegistration.objects.filter(member=request.user, event=event)
                .select_related("event", "ticket")
                .first()
            )
            return Response(
                {
                    "detail": "You are already registered for this event.",
                    "registration": build_registration_payload(existing, request=request) if existing else None,
                },
                status=status.HTTP_409_CONFLICT,
            )

        sync_name_to_account(request.user, registration.attendee_first_name, registration.attendee_last_name)

        if event.allow_secondary_email and registration.attendee_secondary_email:
            sync_secondary_email_to_account(request.user, registration.attendee_secondary_email)

        if event.collect_phone and registration.attendee_phone:
            phone_region = data.get("attendee_phone_region", "1-US")
            sync_phone_to_account(
                request.user, registration.attendee_phone, region=phone_region, verified=phone_verified_inline
            )

        schedule_registration_sync(event)

        try:
            from event.services.ticket_mail import send_ticket_email

            send_ticket_email(registration)
        except Exception:
            logger.exception("Failed to send initial ticket email for registration %s", registration.pk)

        registration.refresh_from_db()
        return Response(build_registration_payload(registration, request=request), status=status.HTTP_201_CREATED)


class MyTicketsView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        registrations = EventRegistration.objects.filter(member=request.user).select_related("event", "ticket")
        return Response([build_registration_payload(r, request=request) for r in registrations])


class SendPhoneCodeView(APIView):
    """Send a verification SMS to a phone number (pre-registration, inline)."""

    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        phone = request.data.get("phone", "").strip()
        region = request.data.get("region", "1-US")
        if not phone:
            return Response({"detail": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)

        phone_error = _validate_phone_digits(phone, region)
        if phone_error:
            return Response({"detail": phone_error}, status=status.HTTP_400_BAD_REQUEST)

        phone = _normalize_phone(phone, region)

        try:
            from authn.services.sms import start_phone_verification
            from authn.services.sms.twilio_verify import PhoneVerificationDeliveryError, PhoneVerificationInvalid

            _clear_phone_verification(request.user, phone)
            start_phone_verification(phone)
        except PhoneVerificationInvalid:
            return Response({"detail": "Invalid phone number."}, status=status.HTTP_400_BAD_REQUEST)
        except PhoneVerificationDeliveryError:
            logger.exception("Failed to send phone verification SMS to %s", phone)
            return Response(
                {"detail": "Failed to send verification code. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception("Failed to send phone verification SMS to %s", phone)
            return Response(
                {"detail": "Failed to send verification code. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"detail": "Verification code sent.", "phone": phone})


class VerifyPhoneCodeView(APIView):
    """Verify a phone SMS code (pre-registration, inline)."""

    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        phone = request.data.get("phone", "").strip()
        code = request.data.get("code", "").strip()
        region = request.data.get("region", "1-US")
        if not phone or not code:
            return Response({"detail": "Phone and code are required."}, status=status.HTTP_400_BAD_REQUEST)

        phone = _normalize_phone(phone, region)

        try:
            from authn.services.sms import check_phone_verification
            from authn.services.sms.twilio_verify import PhoneVerificationInvalid, PhoneVerificationThrottled

            check_phone_verification(phone, code)
        except PhoneVerificationThrottled:
            return Response(
                {"detail": "Too many failed attempts. Please request a new code."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except PhoneVerificationInvalid:
            return Response({"detail": "Invalid or expired verification code."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Phone verification failed for %s", phone)
            return Response(
                {"detail": "Verification service is unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        _mark_phone_verified(request.user, phone)

        return Response({"detail": "Phone verified.", "phone": phone, "verified": True})


class ResendTicketEmailView(APIView):
    permission_classes = [IsAuthenticated]

    # noinspection PyMethodMayBeStatic
    def post(self, request, pk):
        try:
            registration = EventRegistration.objects.select_related("event", "ticket", "member").get(
                pk=pk, member=request.user
            )
        except EventRegistration.DoesNotExist:
            return Response({"detail": "Registration not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            from event.services.ticket_mail import send_ticket_email

            send_ticket_email(registration)
        except Exception:
            logger.exception("Failed to send ticket email for registration %s", pk)
            return Response(
                {"detail": "Failed to send email. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        registration.refresh_from_db()
        return Response(build_registration_payload(registration, request=request))
