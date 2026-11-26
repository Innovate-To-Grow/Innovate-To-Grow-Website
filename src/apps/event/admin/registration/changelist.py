"""Registrations changelist: the semester filter and the search + filter toolbar shown at every width.

Unfold shows ``list_filter`` inline only at its ``2xl`` breakpoint (1536px); narrower windows get a "Filters"
button that opens a sheet. Staff look registrations up by semester or event, so the changelist template renders
those two filters as selects beside the search box (``_changelist_toolbar.html``); the full filter sheet stays
behind the button. Events have no semester field: a semester is derived from the event's start date.
"""

import datetime

from django.contrib import admin
from django.contrib.admin.views.main import ERROR_FLAG, PAGE_VAR, SEARCH_VAR

SEMESTER_PARAM = "semester"
EVENT_PARAM = "event__id__exact"

# (value, label, first month, last month): I2G runs a spring and a fall showcase, so the year splits in two.
_SEASONS = (("fall", "Fall", 7, 12), ("spring", "Spring", 1, 6))
_SEASON_LABELS = {value: label for value, label, _first, _last in _SEASONS}
_SEASON_MONTHS = {value: (first, last) for value, _label, first, last in _SEASONS}


def semester_value(day):
    """``2026-fall`` for any date from July to December 2026, ``2026-spring`` for January to June."""
    season = next(value for value, _label, first, last in _SEASONS if first <= day.month <= last)
    return f"{day.year}-{season}"


def semester_label(value):
    year, season = value.split("-", 1)
    return f"{_SEASON_LABELS[season]} {year}"


def semester_bounds(value):
    """The first and last day of a semester value, or ``None`` when the value is not one."""
    year, _sep, season = (value or "").partition("-")
    months = _SEASON_MONTHS.get(season)
    if months is None or not (year.isdigit() and 1 <= int(year) < datetime.MAXYEAR):
        return None
    first, last = months
    end = datetime.date(int(year) + 1, 1, 1) if last == 12 else datetime.date(int(year), last + 1, 1)
    return datetime.date(int(year), first, 1), end - datetime.timedelta(days=1)


def semester_choices(dates):
    """Newest-first ``(value, label)`` pairs for the semesters the given event dates fall in."""
    values = sorted({semester_value(day) for day in dates}, key=lambda v: (v[:4], v.endswith("fall")), reverse=True)
    return [(value, semester_label(value)) for value in values]


class SemesterListFilter(admin.SimpleListFilter):
    title = "semester"
    parameter_name = SEMESTER_PARAM

    def lookups(self, request, model_admin):
        from ...models import Event

        return semester_choices(Event.objects.values_list("date", flat=True))

    def queryset(self, request, queryset):
        bounds = semester_bounds(self.value())
        if bounds is None:
            return queryset
        start, end = bounds
        return queryset.filter(event__date__gte=start, event__date__lte=end)


def build_toolbar(request, events):
    """Template context for the always-visible search + semester + event toolbar.

    ``hidden`` carries every other query parameter (ticket filter, ordering, popup flags) so submitting the
    toolbar keeps them, the way Unfold's own search form does. The page number is dropped so a new search starts
    on page one, and so is a stale error flag.
    """
    handled = {SEARCH_VAR, SEMESTER_PARAM, EVENT_PARAM, PAGE_VAR, ERROR_FLAG}
    return {
        "search_var": SEARCH_VAR,
        "semester_param": SEMESTER_PARAM,
        "semester_choices": semester_choices(event.date for event in events),
        "semester_selected": request.GET.get(SEMESTER_PARAM, ""),
        "event_param": EVENT_PARAM,
        "event_choices": [(str(event.pk), event.name) for event in events],
        "event_selected": request.GET.get(EVENT_PARAM, ""),
        "hidden": [(name, value) for name, values in request.GET.lists() if name not in handled for value in values],
        "is_filtered": any(request.GET.get(name) for name in (SEARCH_VAR, SEMESTER_PARAM, EVENT_PARAM)),
    }
