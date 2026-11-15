"""Adding an event from a copy of another, and the site-settings context the add and change pages show."""

from django.core.exceptions import ValidationError
from django.http import Http404

from apps.core.models import EmailServiceConfig, GoogleCredentialConfig

from ...models import Event, Question, Ticket
from ...services.template import EventCopyTemplate, build_event_copy_template
from ...services.ticket.date_ranges import format_event_date_range
from .inlines import COPY_INLINE_INITIAL_ATTR

COPY_TEMPLATE_ATTR = "_event_admin_copy_template"


class EventCopyTemplateMixin:
    """The add and change views of ``EventAdmin``: the copy template and the site-settings context."""

    @staticmethod
    def _get_site_settings_context():
        from apps.core.models import AWSCredentialConfig

        email_config = EmailServiceConfig.load()
        google_config = GoogleCredentialConfig.load()
        aws_config = AWSCredentialConfig.load()
        return {
            "email_config": email_config if email_config.pk else None,
            "google_config": google_config if google_config.pk else None,
            "google_configured": google_config.is_configured,
            "aws_config": aws_config if aws_config.pk else None,
        }

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), **self._get_site_settings_context()}
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        copy_template = self._prepare_copy_template(request)
        copy_source_events = [
            {
                "pk": event.pk,
                "name": event.name,
                "date_range": format_event_date_range(event.date, event.effective_end_date),
            }
            for event in Event.objects.order_by("-date", "name")
        ]
        extra_context = {
            **(extra_context or {}),
            **self._get_site_settings_context(),
            "copy_template": copy_template,
            "copy_source_events": copy_source_events,
        }
        return super().add_view(request, form_url, extra_context)

    def _prepare_copy_template(self, request) -> EventCopyTemplate | None:
        if hasattr(request, COPY_TEMPLATE_ATTR):
            return getattr(request, COPY_TEMPLATE_ATTR)

        copy_template = None
        inline_initial = {}

        # ``copy_from`` is only a GET-time template selector. Once the browser
        # has loaded the snapshot, POSTed Event and inline values are the source
        # of truth. This also lets a reviewed form save if the source is deleted
        # in the meantime.
        if request.method == "GET":
            source_id = request.GET.get("copy_from", "").strip()
            if source_id:
                try:
                    source = Event.objects.prefetch_related("tickets", "questions").get(pk=source_id)
                except (Event.DoesNotExist, ValidationError, ValueError) as exc:
                    raise Http404("The Event selected as a copy source does not exist.") from exc

                copy_template = build_event_copy_template(source)
                inline_initial = {
                    Ticket: copy_template.ticket_initial(),
                    Question: copy_template.question_initial(),
                }

        setattr(request, COPY_TEMPLATE_ATTR, copy_template)
        setattr(request, COPY_INLINE_INITIAL_ATTR, inline_initial)
        return copy_template

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        copy_template = self._prepare_copy_template(request)
        if copy_template is None:
            return initial

        initial.update(copy_template.event_initial)
        return initial

    def get_formset_kwargs(self, request, obj, inline, prefix):
        kwargs = super().get_formset_kwargs(request, obj, inline, prefix)
        if request.method == "GET" and (obj is None or obj._state.adding):
            self._prepare_copy_template(request)
            initial_by_model = getattr(request, COPY_INLINE_INITIAL_ATTR, {})
            if inline.model in initial_by_model:
                kwargs["initial"] = initial_by_model[inline.model]
        return kwargs
