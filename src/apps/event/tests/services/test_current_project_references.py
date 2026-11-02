"""Current projects found in bulk (by id, or the active schedule's) read the same as one found by its id."""

import uuid

from django.core.cache import cache
from django.test import TestCase

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.event.services.current_projects import (
    active_schedule_references,
    find_current_project,
    find_current_projects,
)

TRACKS = [{"Track": 1, "Room": "Granite", "Class": "CAP"}, {"Track": 2, "Room": "Cobalt", "Class": "CAP"}]


def _slotted(track, order, team, title, term, **extra):
    return {
        "Track": track,
        "Order": order,
        "Year-Semester": term,
        "Class": "CAP",
        "Team#": team,
        "Project Title": title,
        **extra,
    }


def _listed(team, title):
    # A schedule also lists teams that present in another semester, before they hand anything in.
    return {"Track": "(Fall)", "Order": "(Fall)", "Class": "CAP", "Team#": team, "Project Title": title}


class CurrentProjectReferencesTest(TestCase):
    def setUp(self):
        cache.clear()
        spring = CurrentProjectSchedule.objects.create(name="2026 Spring I2G Event")
        sync_schedule(
            spring,
            tracks_records=TRACKS,
            projects_records=[
                _slotted(1, 1, "101", "Solar Kiln", "2026-1 Spring"),
                _slotted(2, 1, "102", "Seed Counter", "2026-1 Spring"),
                _listed("201", "Power Aspire"),
                _listed("202", "Frequency Ablation Caps"),
            ],
        )
        fall = CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        sync_schedule(
            fall,
            tracks_records=TRACKS,
            projects_records=[
                _slotted(2, 3, "201", "Power Aspire", "2026-2 Fall", **{"Student Names": "Ada Lovelace"}),
                _slotted(1, 2, "301", "Water Sensor", "2026-2 Fall"),
                # A team the sheet lists twice presents in both tracks; the earlier Order is its slot.
                _slotted(2, 1, "302", "Drone Mapper", "2026-2 Fall"),
                _slotted(1, 4, "302", "Drone Mapper", "2026-2 Fall"),
                _listed("401", "Spring Bridge"),
            ],
        )
        self.spring = dict(CurrentProject.objects.filter(schedule=spring).values_list("team_number", "pk"))
        self.fall = dict(CurrentProject.objects.filter(schedule=fall).values_list("team_number", "pk"))

    def _ids(self):
        return [*self.spring.values(), *self.fall.values()]

    def test_each_reference_is_the_one_its_id_finds_alone(self):
        references = find_current_projects(self._ids())

        self.assertEqual(len(references), 8)
        for project_id in self._ids():
            self.assertEqual(references[str(project_id)], find_current_project(project_id))

    def test_references_carry_the_team_record_its_term_and_its_first_slot(self):
        references = find_current_projects(self._ids())

        def summary(project_id):
            reference = references[str(project_id)]
            return reference.project.pk, reference.term, reference.track, reference.order

        self.assertEqual(summary(self.spring["101"]), (self.spring["101"], "2026-1 Spring", 1, 1))
        # Listed in spring, presents in fall: the fall row holds its record.
        self.assertEqual(summary(self.spring["201"]), (self.fall["201"], "2026-2 Fall", 2, 3))
        self.assertEqual(references[str(self.spring["201"])].project.student_names, "Ada Lovelace")
        # Listed in spring and found in no other schedule: its own row, with spring's term and no slot.
        self.assertEqual(summary(self.spring["202"]), (self.spring["202"], "2026-1 Spring", None, None))
        self.assertEqual(summary(self.fall["302"]), (self.fall["302"], "2026-2 Fall", 2, 1))
        # The live schedule holds its own listed teams' records.
        self.assertEqual(summary(self.fall["401"]), (self.fall["401"], "2026-2 Fall", None, None))

    def test_unknown_and_malformed_ids_are_left_out_and_keys_are_the_ids_as_requested(self):
        known = self.spring["101"]

        references = find_current_projects([known, str(known), uuid.uuid4(), "not-a-uuid", None, ""])

        self.assertEqual(list(references), [str(known)])
        self.assertIsNone(find_current_project(uuid.uuid4()))
        self.assertEqual(find_current_projects([]), {})

    def test_query_count_does_not_grow_with_the_ids(self):
        with self.assertNumQueries(4):
            find_current_projects([self.spring["101"], self.spring["201"]])
        with self.assertNumQueries(4):
            find_current_projects(self._ids())
        # Without a listed team of an earlier schedule there is no team record to look up.
        with self.assertNumQueries(3):
            find_current_projects(self.fall.values())


class ActiveScheduleReferencesTest(TestCase):
    def setUp(self):
        cache.clear()
        self.fall = CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        sync_schedule(
            self.fall,
            tracks_records=TRACKS,
            projects_records=[
                _slotted(1, 1, "301", "Water Sensor", "2026-2 Fall"),
                _slotted(2, 2, "302", "Drone Mapper", "2026-2 Fall"),
                _listed("401", "Spring Bridge"),
            ],
        )
        # An earlier schedule's projects are not the active schedule's.
        spring = CurrentProjectSchedule.objects.create(name="2026 Spring I2G Event", is_active=False)
        sync_schedule(
            spring, tracks_records=TRACKS, projects_records=[_slotted(1, 1, "101", "Solar Kiln", "2026-1 Spring")]
        )

    def test_lists_every_project_of_the_active_schedule_with_its_term(self):
        references = active_schedule_references()

        self.assertEqual(
            [(ref.project.team_number, ref.term, ref.track, ref.order) for ref in references],
            [("301", "2026-2 Fall", 1, 1), ("302", "2026-2 Fall", 2, 2), ("401", "2026-2 Fall", None, None)],
        )
        for reference in references:
            self.assertEqual(reference, find_current_project(reference.project.pk))

    def test_no_active_schedule_lists_nothing(self):
        CurrentProjectSchedule.objects.filter(pk=self.fall.pk).update(is_active=False)

        with self.assertNumQueries(1):
            self.assertEqual(active_schedule_references(), [])

    def test_query_count_does_not_grow_with_the_projects(self):
        with self.assertNumQueries(3):
            active_schedule_references()
        CurrentProject.objects.bulk_create(
            CurrentProject(schedule=self.fall, class_code="CAP", team_number=str(500 + n), project_title=f"Team {n}")
            for n in range(10)
        )

        with self.assertNumQueries(3):
            self.assertEqual(len(active_schedule_references()), 13)
