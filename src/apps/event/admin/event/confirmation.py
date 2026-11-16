"""What the event save confirmation lists: the edited fields, and on add every ticket type and question."""

from apps.core.admin.confirmation.diff import compute_formsets_diff

from ...models import Question, Ticket


class EventConfirmationMixin:
    """``get_confirmation_diff`` for ``EventAdmin``."""

    # The add confirmation renders its own, richer per-inline rows below, so skip the generic
    # inline summary ConfirmOnSaveMixin would add — otherwise every ticket and question is listed
    # twice. Change confirmations re-add the generic rows in get_confirmation_diff: they are the
    # only inline coverage there, and an inline-only edit must still produce a non-empty diff or
    # the mixin's no-diff short-circuit saves it with no confirmation at all.
    include_inlines_in_confirmation_diff = False

    def get_confirmation_diff(self, request, obj, form, formsets, action_type):
        diff = super().get_confirmation_diff(request, obj, form, formsets, action_type)
        for row in diff:
            if row["field"] in {"collect_phone", "verify_phone", "require_phone"}:
                row["label"] = f"Phone Number: {row['label']}"
            elif row["field"] in {"allow_secondary_email", "verify_secondary_email", "require_secondary_email"}:
                row["label"] = f"Secondary Email: {row['label']}"
        if action_type != "add":
            return diff + compute_formsets_diff(formsets)

        formsets_by_model = {formset.model: formset for formset in formsets}
        ticket_rows = self._active_inline_rows(formsets_by_model.get(Ticket))
        question_rows = self._active_inline_rows(formsets_by_model.get(Question))

        if ticket_rows:
            ticket_rows.sort(key=lambda row: (row.get("order", 0), row.get("name", "")))
            diff.extend(
                {
                    "field": f"tickets.{index}",
                    "label": f"Ticket type {index}",
                    "new_value": f"{row['name']} — order {row.get('order', 0)}",
                }
                for index, row in enumerate(ticket_rows, start=1)
            )
        else:
            diff.append({"field": "tickets", "label": "Ticket types", "new_value": "None"})

        if question_rows:
            question_rows.sort(key=lambda row: (row.get("order", 0), row.get("text", "")))
            diff.extend(
                {
                    "field": f"questions.{index}",
                    "label": f"Question {index}",
                    "new_value": (
                        f"{row['text']} — required: {'Yes' if row.get('is_required') else 'No'}; "
                        f"order {row.get('order', 0)}"
                    ),
                }
                for index, row in enumerate(question_rows, start=1)
            )
        else:
            diff.append({"field": "questions", "label": "Questions", "new_value": "None"})

        return diff

    @staticmethod
    def _active_inline_rows(formset):
        if formset is None:
            return []
        rows = []
        for inline_form in formset.forms:
            cleaned_data = getattr(inline_form, "cleaned_data", None) or {}
            if cleaned_data.get("DELETE"):
                continue
            if inline_form.empty_permitted and not inline_form.has_changed():
                continue
            rows.append(cleaned_data)
        return rows
