from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_.contacts import ContactWriteError, set_phone_flags
from apps.authn.services.members.import_.review.analysis.risky import RISKY_TYPES
from apps.authn.services.members.import_.review.apply.execute import RowWriteError, execute_creations, execute_update
from apps.authn.services.members.import_.review.plan.actions import CREATE, UPDATE, Op, RowPlan
from apps.authn.services.members.import_.review.staging.selection import ForgedSelection, clean_selection, plan_for
from apps.authn.tests.services.members.import_.contact_warnings.test_phone_verified import CELLS
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


class StoredNumberTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.verified = self.phone(self.ada, "2095550101", verified=True, subscribe=True)
        self.unverified = self.phone(self.ada, "2095550102", verified=False, subscribe=True)

    def _row(self, number, cell, **cells):
        return row("ada@example.com", Phone_Number=number, Phone_Verified=cell, **cells)

    def test_a_number_keeps_its_status_and_is_never_offered_a_tick_for_any_cell_value(self):
        for cell in CELLS:
            for phone in (self.verified, self.unverified):
                with self.subTest(cell=cell, verified=phone.verified):
                    analysis = self.analyse_one(self._row(phone.phone_number, cell))
                    (outcome,) = self.apply([self._row(phone.phone_number, cell)])

                    self.assertEqual((analysis.status, analysis.risky), ("no_change", {}))
                    self.assertEqual(outcome.outcome, "no_change")
                    self.assertEqual(outcome.notes, [])
                    stored = ContactPhone.objects.get(pk=phone.pk)
                    self.assertEqual(stored.verified, phone.verified)

    def test_a_posted_verify_or_unverify_tick_for_a_number_is_forged(self):
        for phone, cell, code in ((self.unverified, "TRUE", "R9"), (self.verified, "FALSE", "R6")):
            with self.subTest(code=code):
                analysis = self.analyse_one(self._row(phone.phone_number, cell))

                with self.assertRaisesMessage(ForgedSelection, "is not one of this row's risky changes"):
                    clean_selection(analysis, "update", [f"{code}:{phone.pk}"])

    def test_a_tick_that_reaches_the_planner_anyway_changes_nothing(self):
        analysis = self.analyse_one(self._row(self.unverified.phone_number, "TRUE"))
        ticks = [f"R9:{self.unverified.pk}", f"R6:{self.verified.pk}"]

        plan = plan_for(analysis, "update", ticks)
        (outcome,) = self.apply([self._row(self.unverified.phone_number, "TRUE")], {2: ("update", ticks)})

        self.assertEqual((plan.ops, plan.changes, dict(plan.listed)), ([], [], {}))
        self.assertEqual(outcome.outcome, "no_change")
        self.assertEqual(
            sorted(self.ada.contact_phones.values_list("phone_number", "verified")),
            [("2095550101", True), ("2095550102", False)],
        )

    def test_phone_subscribed_still_applies_and_leaves_verified_alone(self):
        (outcome,) = self.apply([self._row(self.verified.phone_number, "FALSE", Phone_Subscribed="FALSE")])

        self.verified.refresh_from_db()
        self.assertEqual((self.verified.subscribe, self.verified.verified), (False, True))
        self.assertEqual(outcome.changes, ["Unsubscribes +12095550101"])

    def test_re_subscribing_a_number_is_still_its_own_tick(self):
        ContactPhone.objects.filter(pk=self.unverified.pk).update(subscribe=False)
        cells_row = self._row(self.unverified.phone_number, "TRUE", Phone_Subscribed="TRUE")

        analysis = self.analyse_one(cells_row)
        (outcome,) = self.apply([cells_row], {2: ("update", [f"R5:{self.unverified.pk}"])})

        self.assertEqual([item["id"] for item in analysis.risky[str(self.ada.pk)]], [f"R5:{self.unverified.pk}"])
        self.unverified.refresh_from_db()
        self.assertEqual((self.unverified.subscribe, self.unverified.verified), (True, False))
        self.assertEqual(outcome.changes, ["Re-subscribes +12095550102"])

    def test_a_new_number_for_an_existing_member_is_added_unverified(self):
        (outcome,) = self.apply([self._row("2095550199", "TRUE")])

        self.assertFalse(ContactPhone.objects.get(phone_number="2095550199").verified)
        self.assertFalse(any("Phone Verified" in note or "added unverified" in note for note in outcome.notes))

    def test_email_addresses_still_have_their_verify_and_unverify_ticks(self):
        work = self.email(self.ada, "ada.work@example.com", verified=False)
        primary = ContactEmail.objects.get(email_address="ada@example.com")
        cells_row = row(
            "ada@example.com",
            Primary_Verified="FALSE",
            Secondary_Email="ada.work@example.com",
            Secondary_Verified="TRUE",
            Phone_Number="2095550102",
            Phone_Verified="TRUE",
        )

        items = {item["id"]: item for item in self.analyse_one(cells_row).risky[str(self.ada.pk)]}

        self.assertEqual(set(items), {f"R6:{primary.pk}", f"R9:{work.pk}"})
        self.assertEqual(RISKY_TYPES["R6"], "Mark email addresses unverified")
        self.assertEqual(RISKY_TYPES["R9"], "Mark email addresses verified (each becomes a sign-in factor)")


class GuardedWriteTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.phone_record = self.phone(self.ada, "2095550101", verified=False, subscribe=True)

    def test_set_phone_flags_refuses_verified_in_either_direction(self):
        verified = self.phone(self.ada, "2095550102", verified=True, subscribe=True)
        for phone, data in (
            (self.phone_record, {"verified": True}),
            (verified, {"verified": False}),
            (self.phone_record, {"subscribe": False, "verified": True}),
        ):
            with self.subTest(data=data):
                with self.assertRaisesMessage(
                    ContactWriteError, "an import may not change a phone number's verified flag"
                ):
                    set_phone_flags(self.ada, str(phone.pk), data)

                stored = ContactPhone.objects.get(pk=phone.pk)
                self.assertEqual((stored.verified, stored.subscribe), (phone.verified, True))

    def test_set_phone_flags_still_writes_subscribe(self):
        set_phone_flags(self.ada, str(self.phone_record.pk), {"subscribe": False})

        self.phone_record.refresh_from_db()
        self.assertEqual((self.phone_record.subscribe, self.phone_record.verified), (False, False))

    def test_an_update_op_carrying_verified_fails_the_row(self):
        plan = RowPlan(UPDATE, target=str(self.ada.pk))
        plan.add(Op("phone_flags", ref=str(self.phone_record.pk), data={"verified": True}), "forged")

        with self.assertRaisesMessage(RowWriteError, "Row 2: an import may not change a phone number's verified flag"):
            execute_update(2, plan, self.ada)

        self.phone_record.refresh_from_db()
        self.assertFalse(self.phone_record.verified)

    def test_a_creation_op_carrying_verified_still_writes_the_number_unverified(self):
        fields = {
            "first_name": "Nina",
            "middle_name": "",
            "last_name": "New",
            "title": "",
            "organization": "",
            "is_active": True,
            "date_joined": None,
        }
        plan = RowPlan(CREATE)
        plan.add(Op("create_member", data=fields), "Creates the member Nina New")
        data = {"number": "2095550188", "region": "1-US", "verified": True, "subscribe": True}
        plan.add(Op("add_phone", data=data), "Phone +12095550188")

        members = execute_creations([(2, plan)], "!")

        phone = ContactPhone.objects.get(phone_number="2095550188")
        self.assertEqual((phone.member, phone.verified, phone.subscribe), (members[2], False, True))
        self.assertTrue(Member.objects.filter(first_name="Nina", last_name="New").exists())
