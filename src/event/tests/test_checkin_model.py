from django.db import IntegrityError, transaction
from django.test import TestCase

from event.models import CheckIn, CheckInRecord
from event.tests.helpers import make_event, make_member, make_registration, make_ticket


class CheckInRecordModelTest(TestCase):
    def test_registration_can_only_be_checked_in_once_event_wide(self):
        event = make_event(name="Unique Check-in Event")
        ticket = make_ticket(event)
        member = make_member(email="unique-checkin@example.com")
        registration = make_registration(member, event, ticket)
        first_station = CheckIn.objects.create(event=event, name="Main Entrance")
        second_station = CheckIn.objects.create(event=event, name="Side Entrance")
        CheckInRecord.objects.create(check_in=first_station, registration=registration)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CheckInRecord.objects.create(check_in=second_station, registration=registration)
