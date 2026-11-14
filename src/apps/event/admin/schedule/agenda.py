"""The agenda rows of a current-project schedule: their form, the ordering rules of the formset, and the inline."""

from django import forms
from django.db.models import F, Max
from django.forms import BaseInlineFormSet
from unfold.admin import TabularInline

from apps.core.admin import AppAccessInlineMixin

from ...models import EventAgendaItem

MAX_DISPLAY_ORDER = 9999
ORDER_KEY_FIELDS = {"section_type", "display_order"}


class EventAgendaItemForm(forms.ModelForm):
    class Meta:
        model = EventAgendaItem
        fields = ("section_type", "display_order", "time_label", "title", "location")
        help_texts = {
            "section_type": "Expo fills the “EXPO: POSTERS AND DEMOS” table; Awards fills “AWARDS & RECEPTION”.",
            "display_order": "Row order within its table, lowest first. Leave blank on a new row to add it at the end.",
            "location": "The table's “Room:” header shows the location of its first row.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance._state.adding:
            order = self.fields["display_order"]
            order.required = False
            order.widget.attrs["placeholder"] = "end"
            # A blank first choice (the model field has none), so a row nobody touched is not "changed" and is ignored.
            section_type = self.fields["section_type"]
            section_type.choices = [("", "---------"), *section_type.choices]

    def clean_display_order(self):
        order = self.cleaned_data["display_order"]
        # Only a value being entered is capped, so an older row above the cap stays editable.
        if order is not None and order > MAX_DISPLAY_ORDER and "display_order" in self.changed_data:
            raise forms.ValidationError(f"Use a number up to {MAX_DISPLAY_ORDER}.")
        return order


class EventAgendaItemFormSet(BaseInlineFormSet):
    """Order rows by ``display_order`` — unique per (schedule, table) — without the editor juggling numbers.

    * A new row left blank is appended after the last one, in the order the rows were entered.
    * Rows may be swapped, shifted or moved between tables in one save. The unique constraint is checked row by
      row while saving, so the rows being rewritten are first moved out of the way (see ``save_existing_objects``).
    * A new or moved row that lands on an order held by a row this page never loaded (another editor added it
      since) is reported as a form error instead of failing at the database. Two saves that commit in the same
      instant can still collide; that surfaces as a server error and the editor just saves again.
    """

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        if index is None or index >= self.initial_form_count():
            # Blank, not the model default of 0 — which would clash with the first row (see ``clean``).
            kwargs["initial"] = {**kwargs.get("initial", {}), "display_order": None}
        return kwargs

    def _live_forms(self):
        """Forms that will leave a row behind: filled in, valid and not marked for deletion."""
        return [
            form for form in self.forms if form.is_valid() and form.cleaned_data and not self._should_delete_form(form)
        ]

    def clean(self):
        live = self._live_forms()
        moving = [form for form in live if form.instance._state.adding or ORDER_KEY_FIELDS & set(form.changed_data)]
        if moving:
            held_elsewhere = self._orders_held_outside_submission()
            self._append_blank_orders(live, held_elsewhere)
            for form in moving:
                if (form.cleaned_data["section_type"], form.cleaned_data["display_order"]) in held_elsewhere:
                    form.add_error("display_order", "Another row of this table already uses this display order.")
        self._flag_rows_sharing_an_order(live)

    @staticmethod
    def _flag_rows_sharing_an_order(live):
        """Report rows of one table with the same order.

        Django's own check skips rows marked for deletion only while the whole formset is valid, so it
        would blame a row that is about to be deleted as soon as any other row has an error.
        """
        rows_by_key = {}
        for form in live:
            if "display_order" in form.cleaned_data:  # gone if the check above already rejected this row
                key = (form.cleaned_data["section_type"], form.cleaned_data["display_order"])
                rows_by_key.setdefault(key, []).append(form)
        for forms_sharing in rows_by_key.values():
            if len(forms_sharing) > 1:
                for form in forms_sharing:
                    form.add_error("display_order", "Two rows of the same table share a display order.")

    def _orders_held_outside_submission(self):
        if self.instance._state.adding:
            return set()
        submitted = [form.instance.pk for form in self.initial_forms]
        rows = EventAgendaItem.objects.filter(config=self.instance).exclude(pk__in=submitted)
        return set(rows.values_list("section_type", "display_order"))

    @staticmethod
    def _append_blank_orders(live, held_elsewhere):
        taken = [order for _, order in held_elsewhere]
        taken += [form.cleaned_data["display_order"] for form in live if form.cleaned_data["display_order"] is not None]
        next_order = max(taken, default=-1) + 1
        for form in live:
            if form.cleaned_data["display_order"] is None:
                form.cleaned_data["display_order"] = form.instance.display_order = next_order
                next_order += 1

    def save_existing_objects(self, commit=True):
        if commit:
            rewritten = [
                form.instance.pk
                for form in self.initial_forms
                if self._should_delete_form(form) or ORDER_KEY_FIELDS & set(form.changed_data)
            ]
            if rewritten:
                # Park above every order that exists or is about to be written, so a parked row can never
                # meet another row's final order while the rest are rewritten.
                top = EventAgendaItem.objects.filter(config=self.instance).aggregate(top=Max("display_order"))["top"]
                finals = [form.cleaned_data["display_order"] for form in self._live_forms()]
                offset = max([top or 0, *finals]) + 1
                EventAgendaItem.objects.filter(pk__in=rewritten).update(display_order=F("display_order") + offset)
        return super().save_existing_objects(commit)


class EventAgendaItemInline(AppAccessInlineMixin, TabularInline):
    """The Expo / Awards tables on the schedule page — text the Google Sheet does not carry.

    Editing here is permanent: ``sync_schedule`` seeds these rows once (first sync) and never rewrites them.
    Deleting rows stays allowed although the schedule admin itself cannot be deleted.
    """

    model = EventAgendaItem
    form = EventAgendaItemForm
    formset = EventAgendaItemFormSet
    extra = 0
    ordering = ("section_type", "display_order")
    verbose_name = "Agenda item"
    verbose_name_plural = "Agenda items (Expo and Awards tables on the schedule page)"
