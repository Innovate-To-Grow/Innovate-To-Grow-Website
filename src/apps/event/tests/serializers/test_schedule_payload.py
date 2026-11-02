from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.serializers import build_schedule_payload
from apps.event.services import sync_schedule


def _record(track, order, team, title, **extra):
    return {
        "Track": track,
        "Order": order,
        "Year-Semester": "2026-2 Fall",
        "Class": "CAP",
        "Team#": team,
        "Project Title": title,
        **extra,
    }


class ScheduleProjectRowsTest(TestCase):
    """Each project of the schedule is listed once, however its presenting flag was edited."""

    def setUp(self):
        cache.clear()
        self.config = CurrentProjectSchedule.objects.create(name="Fall Showcase")
        sync_schedule(
            self.config,
            tracks_records=[{"Track": 1, "Room": "Granite", "Class": "CAP"}],
            projects_records=[
                _record(1, 1, "201", "Water Sensor"),
                {"Track": "", "Order": "", "Class": "CAP", "Team#": "101", "Project Title": "Solar Kiln"},
            ],
        )

    def _rows(self):
        return {(row["team_number"], row["is_presenting"], row["track"]) for row in self._payload()["projects"]}

    def _payload(self):
        return build_schedule_payload(CurrentProjectSchedule.objects.get(pk=self.config.pk))

    def test_baseline_lists_each_team_once(self):
        self.assertEqual(self._rows(), {("201", True, 1), ("101", False, 0)})

    def test_unticking_presenting_on_a_scheduled_team_keeps_one_row(self):
        CurrentProject.objects.filter(team_number="201").update(is_presenting=False)

        rows = self._payload()["projects"]

        self.assertEqual([row["team_number"] for row in rows].count("201"), 1)
        self.assertEqual(self._rows(), {("201", False, 1), ("101", False, 0)})

    def test_ticking_presenting_on_an_unscheduled_team_keeps_it_listed(self):
        CurrentProject.objects.filter(team_number="101").update(is_presenting=True)

        self.assertEqual(self._rows(), {("201", True, 1), ("101", True, 0)})

    def test_unscheduled_rows_carry_the_schedule_term(self):
        rows = {row["team_number"]: row for row in self._payload()["projects"]}

        self.assertEqual(rows["201"]["year_semester"], "2026-2 Fall")
        self.assertEqual(rows["101"]["year_semester"], "2026-2 Fall")


class ScheduleQueryCountTest(TestCase):
    """The schedule endpoint reads slots from the prefetch, so its query count does not grow with the tracks."""

    def setUp(self):
        cache.clear()

    def _sync(self, track_count):
        config = CurrentProjectSchedule.objects.create(name=f"{track_count} tracks")
        sync_schedule(
            config,
            tracks_records=[{"Track": n, "Room": f"Room {n}", "Class": "CAP"} for n in range(1, track_count + 1)],
            projects_records=[
                _record(n, order, f"{n}{order:02d}", f"Project {n}-{order}")
                for n in range(1, track_count + 1)
                for order in (1, 2)
            ],
        )
        return config

    def _query_count(self, config):
        client = APIClient()
        with CaptureQueriesContext(connection) as queries:
            response = client.get("/event/schedule/", {"schedule_id": str(config.pk)})
        self.assertEqual(response.status_code, 200)
        return len(queries)

    # With the request limiter on, the first request of a process also loads its policy rows.
    @override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
    def test_query_count_is_independent_of_track_count(self):
        few = self._query_count(self._sync(2))
        many = self._query_count(self._sync(6))

        self.assertEqual(few, many)
