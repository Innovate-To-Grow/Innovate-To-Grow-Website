"""Ticket and question inlines on the event admin; they follow the event admin's permissions."""

from unfold.admin import TabularInline

from ...models import Event, Question, Ticket

COPY_INLINE_INITIAL_ATTR = "_event_admin_copy_inline_initial"


class EventRelatedInlineMixin:
    """Delegate inline permissions to the registered Event ModelAdmin.

    Default Django inlines require ``event.add_ticket`` / ``change_ticket`` / etc.
    This project grants Event access via :class:`BaseModelAdmin` (typically ``is_staff``),
    so staff without those Ticket codenames would otherwise miss Tickets/Questions blocks.
    """

    def _event_model_admin(self):
        return self.admin_site._registry.get(Event)

    def has_view_permission(self, request, obj=None):
        ma = self._event_model_admin()
        if ma is None:
            return super().has_view_permission(request, obj)
        return ma.has_view_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        ma = self._event_model_admin()
        if ma is None:
            return super().has_add_permission(request, obj)
        if obj is None:
            return ma.has_add_permission(request)
        return ma.has_change_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        ma = self._event_model_admin()
        if ma is None:
            return super().has_change_permission(request, obj)
        if obj is None:
            return ma.has_add_permission(request)
        return ma.has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        ma = self._event_model_admin()
        if ma is None:
            return super().has_delete_permission(request, obj)
        if obj is None:
            return ma.has_add_permission(request)
        return ma.has_change_permission(request, obj)

    def get_extra(self, request, obj=None, **kwargs):
        initial_by_model = getattr(request, COPY_INLINE_INITIAL_ATTR, {})
        if (obj is None or obj._state.adding) and self.model in initial_by_model:
            return len(initial_by_model[self.model])
        return super().get_extra(request, obj, **kwargs)


class TicketInline(EventRelatedInlineMixin, TabularInline):
    model = Ticket
    extra = 0
    fields = ("name", "order")


class QuestionInline(EventRelatedInlineMixin, TabularInline):
    model = Question
    extra = 0
    fields = ("text", "is_required", "order")
