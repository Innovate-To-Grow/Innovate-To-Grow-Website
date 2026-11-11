"""A row whose member was found, but which still needs a decision: C6 (name), C7 (Row 5), C8 (unlinked), C9 (mode).

Each conflict starts on "skip"; its options say what a choice would do, and are disabled (with the reason) when the
actor may not change that member. The apply tests check what each choice writes.
"""

from django.core import mail

from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.services.members.import_.review.choices import NEEDS_NAMES, NO_CHANGE_PERMISSION, PRIVILEGED
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row

UUID_HEADERS = [*HEADERS, "Member UUID"]
UNVERIFIED = (
    "Not verified. The member can verify it on /account, or an admin can mark it verified in Contact Emails first."
)


def uuid_row(primary, member_uuid, **cells):
    return [*row(primary, **cells), str(member_uuid) if member_uuid else None]


def options(analysis) -> dict:
    return {item["value"]: item for item in analysis.options}


def not_privileged(member) -> bool:
    return not (member.is_staff or member.is_superuser)


def roles(member) -> dict:
    return dict(member.contact_emails.values_list("email_address", "email_type"))


class NameDiffersTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.label = f"Ada Lovelace (member {self.ada.pk})"
        self.renamed = row("ada@example.com", First_Name="Augusta", Last_Name="King", Organization="Engines")

    def test_found_by_email_with_another_name(self):
        analysis = self.analyse_one(self.renamed)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "name_differs", "skip")
        )
        self.assertEqual((analysis.target, analysis.facts["matched_by"]), (str(self.ada.pk), "primary"))
        self.assertEqual(list(options(analysis)), ["update_same_person", "update_keep_name", "skip"])
        self.assertEqual(
            [item["label"] for item in analysis.options[:2]],
            [
                f"Same person: update {self.label}, including the name",
                f"Same person: update {self.label}, keep their name",
            ],
        )
        self.assertEqual(
            options(analysis)["skip"]["hint"], "Not the same person, or not sure. The address stays with the member."
        )
        self.assertTrue(all(item["enabled"] and not item["suggested"] for item in analysis.options))

    def test_updating_needs_permission(self):
        analysis = self.analyse_one(self.renamed, can_update=False)

        self.assertEqual(
            [item["reason"] for item in analysis.options], [NO_CHANGE_PERMISSION, NO_CHANGE_PERMISSION, ""]
        )

    def test_found_through_a_secondary_address(self):
        self.email(self.ada, "ada.work@example.com")

        analysis = self.analyse_one(row("ada.work@example.com", First_Name="Augusta", Last_Name="King"))

        self.assertEqual((analysis.conflict, analysis.facts["matched_by"]), ("name_differs", "secondary"))

    def test_same_person_including_the_name(self):
        (outcome,) = self.apply([self.renamed], {2: ("update_same_person", [])})

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(
            (self.ada.first_name, self.ada.last_name, self.ada.organization), ("Augusta", "King", "Engines")
        )

    def test_same_person_keeping_their_name(self):
        (outcome,) = self.apply([self.renamed], {2: ("update_keep_name", [])})

        self.ada.refresh_from_db()
        self.assertEqual(
            (self.ada.first_name, self.ada.last_name, self.ada.organization), ("Ada", "Lovelace", "Engines")
        )
        self.assertIn("The sheet's name is not applied; Ada Lovelace is kept", outcome.notes)

    def test_skipped_by_default(self):
        (outcome,) = self.apply([self.renamed])

        self.assertEqual(outcome.outcome, "skipped")
        self.ada.refresh_from_db()
        self.assertEqual((self.ada.first_name, self.ada.organization), ("Ada", None))


class AddressNotPrimaryTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.label = f"Ada Lovelace (member {self.ada.pk})"
        self.work = self.email(self.ada, "ada.work@example.com", verified=True, subscribe=True)

    def test_the_address_is_the_members_secondary(self):
        analysis = self.analyse_one(row("ada.work@example.com"))

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "address_not_primary", "skip")
        )
        self.assertEqual(
            (analysis.target, analysis.facts["matched_by"], analysis.facts["record"]),
            (str(self.ada.pk), "secondary", str(self.work.pk)),
        )
        self.assertEqual(list(options(analysis)), ["update", "update_make_primary", "skip"])
        update, promote = analysis.options[:2]
        self.assertEqual(update["label"], f"Update {self.label}; keep the email roles")
        self.assertEqual(
            update["hint"], "The flag cells apply to ada.work@example.com; the primary ada@example.com is kept."
        )
        self.assertEqual((update["enabled"], update["suggested"]), (True, True))
        self.assertEqual(promote["label"], f"Update {self.label} and make ada.work@example.com their primary")
        self.assertEqual((promote["enabled"], promote["suggested"]), (True, False))
        self.assertEqual(
            analysis.facts["why"],
            f"ada.work@example.com is the secondary email of {self.label}, whose primary email is ada@example.com.",
        )

    def test_an_other_address_too(self):
        self.email(self.ada, "ada.old@example.com", "other")

        analysis = self.analyse_one(row("ada.old@example.com"))

        self.assertEqual((analysis.conflict, analysis.facts["matched_by"]), ("address_not_primary", "other"))

    def test_making_an_unverified_address_primary_is_disabled(self):
        ContactEmail.objects.filter(pk=self.work.pk).update(verified=False)

        analysis = self.analyse_one(row("ada.work@example.com"))

        self.assertTrue(options(analysis)["update"]["enabled"])
        self.assertEqual(
            (options(analysis)["update_make_primary"]["enabled"], options(analysis)["update_make_primary"]["reason"]),
            (False, UNVERIFIED),
        )

    def test_updating_needs_permission(self):
        analysis = self.analyse_one(row("ada.work@example.com"), can_update=False)

        self.assertEqual(
            [item["reason"] for item in analysis.options], [NO_CHANGE_PERMISSION, NO_CHANGE_PERMISSION, ""]
        )

    def test_a_member_uuid_whose_member_owns_the_address_as_secondary(self):
        analysis = self.analyse_one(uuid_row("ada.work@example.com", self.ada.pk), UUID_HEADERS)

        self.assertEqual((analysis.conflict, analysis.facts["matched_by"]), ("address_not_primary", "uuid"))

    def test_row5_update_keeps_every_address_and_its_role(self):
        cells_row = row(
            "ada.work@example.com", Organization="Spirit", Primary_Verified="TRUE", Primary_Subscribed="FALSE"
        )

        (outcome,) = self.apply([cells_row], {2: ("update", [])})

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Spirit")
        self.assertEqual(roles(self.ada), {"ada@example.com": "primary", "ada.work@example.com": "secondary"})
        self.work.refresh_from_db()
        primary = ContactEmail.objects.get(email_address="ada@example.com")
        self.assertEqual((self.work.verified, self.work.subscribe), (True, False))
        self.assertEqual((primary.verified, primary.subscribe), (True, True))
        self.assertEqual(mail.outbox, [])

    def test_the_flag_cells_never_reach_the_current_primary(self):
        cells_row = row("ada.work@example.com", Primary_Verified="FALSE", Primary_Subscribed="FALSE")

        (outcome,) = self.apply([cells_row], {2: ("update", [])})

        primary = ContactEmail.objects.get(email_address="ada@example.com")
        self.work.refresh_from_db()
        self.assertEqual((primary.verified, primary.subscribe), (True, True))
        self.assertEqual((self.work.verified, self.work.subscribe), (True, False))
        self.assertIn(
            "Primary Verified is FALSE, but ada.work@example.com is verified; left verified (un-verifying needs its "
            "tick)",
            outcome.notes,
        )

    def test_make_primary_promotes_the_address_and_demotes_the_old_ones(self):
        old = self.email(self.ada, "ada.old@example.com", "other", verified=True)

        (outcome,) = self.apply([row("ada.old@example.com")], {2: ("update_make_primary", [])})

        self.assertEqual(outcome.outcome, "updated")
        self.assertEqual(
            roles(self.ada),
            {"ada.old@example.com": "primary", "ada@example.com": "secondary", "ada.work@example.com": "other"},
        )
        self.assertIn(
            "Makes ada.old@example.com the primary email; the previous primary ada@example.com becomes secondary; the "
            'previous secondary ada.work@example.com becomes "other"; nothing is deleted',
            outcome.changes,
        )
        self.assertEqual(outcome.listed["primary_changes"], ["ada.old@example.com made primary"])
        old.refresh_from_db()
        self.assertTrue(old.verified)

    def test_make_primary_for_a_member_without_a_primary(self):
        lee = self.member("Lee", "Legacy")
        self.email(lee, "lee.old@example.com", verified=True)

        (outcome,) = self.apply(
            [row("lee.old@example.com", First_Name="Lee", Last_Name="Legacy")], {2: ("update_make_primary", [])}
        )

        self.assertEqual(roles(lee), {"lee.old@example.com": "primary"})
        self.assertIn("Makes lee.old@example.com the primary email; nothing is deleted", outcome.changes)

    def test_make_primary_of_the_secondary_swaps_the_two(self):
        (outcome,) = self.apply([row("ada.work@example.com")], {2: ("update_make_primary", [])})

        self.assertEqual(roles(self.ada), {"ada.work@example.com": "primary", "ada@example.com": "secondary"})
        self.assertIn(
            "Makes ada.work@example.com the primary email; the previous primary ada@example.com becomes secondary; "
            "nothing is deleted",
            outcome.changes,
        )

    def test_skipped_by_default(self):
        (outcome,) = self.apply([row("ada.work@example.com", Organization="Spirit")])

        self.assertEqual(outcome.outcome, "skipped")
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)


class UnlinkedAddressTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.loose = ContactEmail.objects.create(
            member=None, email_address="loose@example.com", verified=True, subscribe=False
        )
        self.claim = f"create_claim:{self.loose.pk}"
        self.lin = {"First_Name": "Lin", "Last_Name": "Loose"}

    def test_an_address_with_no_member(self):
        analysis = self.analyse_one(row("loose@example.com", **self.lin))

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "unlinked_address", "skip")
        )
        self.assertEqual((analysis.facts["record"], analysis.facts["attach_candidates"]), (str(self.loose.pk), []))
        self.assertEqual(list(options(analysis)), [self.claim, "skip"])
        claim = options(analysis)[self.claim]
        self.assertEqual(claim["label"], "Create a new member and attach loose@example.com as their primary")
        self.assertEqual((claim["enabled"], claim["suggested"]), (True, True))
        self.assertTrue(analysis.facts["why"].startswith("loose@example.com is a contact email with no member (added "))

    def test_creating_a_member_needs_both_names(self):
        analysis = self.analyse_one(row("loose@example.com", First_Name="Lin", Last_Name=None))

        claim = options(analysis)[self.claim]
        self.assertEqual((claim["enabled"], claim["reason"], claim["suggested"]), (False, NEEDS_NAMES, False))

    def test_members_found_through_the_secondary_and_phone_cells_can_take_the_address(self):
        grace = self.member("Grace", "Hopper", "grace@example.com")
        self.email(grace, "grace.work@example.com")
        self.phone(grace, "2095550101")
        cells_row = row(
            "loose@example.com", Secondary_Email="ada@example.com", Phone_Number="(209) 555-0101", **self.lin
        )

        analysis = self.analyse_one(cells_row)

        self.assertEqual(analysis.facts["attach_candidates"], [str(self.ada.pk), str(grace.pk)])
        self.assertEqual(
            list(options(analysis)), [self.claim, f"attach_to:{self.ada.pk}", f"attach_to:{grace.pk}", "skip"]
        )
        self.assertEqual(
            [item["label"] for item in analysis.options[1:3]],
            [
                f'Attach loose@example.com to Ada Lovelace (member {self.ada.pk}) as "secondary" and update them '
                "(their name is kept)",
                f'Attach loose@example.com to Grace Hopper (member {grace.pk}) as "other" and update them (their name '
                "is kept)",
            ],
        )
        self.assertTrue(all(item["enabled"] for item in analysis.options))

    def test_attaching_needs_permission(self):
        sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        cells_row = row("loose@example.com", Secondary_Email="sam@example.com", **self.lin)

        refused = self.analyse_one(cells_row, can_update=False)
        not_master = self.analyse_one(cells_row, can_manage=not_privileged)

        self.assertEqual(options(refused)[f"attach_to:{sam.pk}"]["reason"], NO_CHANGE_PERMISSION)
        self.assertTrue(options(refused)[self.claim]["enabled"])
        self.assertEqual(options(not_master)[f"attach_to:{sam.pk}"]["reason"], PRIVILEGED)

    def test_a_member_uuid_offers_its_member_and_blocks_a_new_member(self):
        """C8 also when the Member UUID names a member: "attach to" it is offered, "create a new member" is not."""
        analysis = self.analyse_one(uuid_row("loose@example.com", self.ada.pk, **self.lin), UUID_HEADERS)

        self.assertEqual((analysis.status, analysis.conflict), ("needs_decision", "unlinked_address"))
        self.assertEqual(options(analysis)[self.claim]["reason"], "The row's Member UUID names an existing member")
        self.assertTrue(options(analysis)[f"attach_to:{self.ada.pk}"]["enabled"])

    def test_create_claim_makes_the_address_the_new_members_primary(self):
        (outcome,) = self.apply([row("loose@example.com", **self.lin)], {2: (self.claim, [])})

        self.assertEqual(outcome.outcome, "created")
        self.loose.refresh_from_db()
        self.assertEqual((self.loose.member, self.loose.email_type), (outcome.member, "primary"))
        self.assertEqual((outcome.member.first_name, outcome.member.last_name), ("Lin", "Loose"))
        # A blank Verified cell never carries the record's old "verified"; a blank Subscribed cell keeps the record's.
        self.assertEqual((self.loose.verified, self.loose.subscribe), (False, False))

    def test_create_claim_takes_the_flag_cells(self):
        cells_row = row("loose@example.com", Primary_Verified="TRUE", Primary_Subscribed="TRUE", **self.lin)

        self.apply([cells_row], {2: (self.claim, [])})

        self.loose.refresh_from_db()
        self.assertEqual((self.loose.verified, self.loose.subscribe), (True, True))

    def test_attach_to_a_member_keeps_their_name_and_adds_the_address_unverified(self):
        cells_row = row("loose@example.com", Secondary_Email="ada@example.com", Organization="Engines", **self.lin)

        (outcome,) = self.apply([cells_row], {2: (f"attach_to:{self.ada.pk}", [])})

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(
            (self.ada.first_name, self.ada.last_name, self.ada.organization), ("Ada", "Lovelace", "Engines")
        )
        self.loose.refresh_from_db()
        self.assertEqual(
            (self.loose.member, self.loose.email_type, self.loose.verified), (self.ada, "secondary", False)
        )
        self.assertIn("The sheet's name is not applied; Ada Lovelace is kept", outcome.notes)

    def test_skipped_by_default(self):
        before = Member.objects.count()

        (outcome,) = self.apply([row("loose@example.com", **self.lin)])

        self.assertEqual((outcome.outcome, Member.objects.count()), ("skipped", before))
        self.loose.refresh_from_db()
        self.assertIsNone(self.loose.member)


class SkipModeTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.label = f"Ada Lovelace (member {self.ada.pk})"

    def test_an_existing_member_when_the_upload_said_to_skip_them(self):
        analysis = self.analyse_one(row("ada@example.com", Organization="Engines"), mode=SKIP_EXISTING)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "exists_but_skip_mode", "skip")
        )
        self.assertEqual(list(options(analysis)), ["skip", "update"])
        self.assertEqual(
            options(analysis)["skip"]["hint"], "The upload said to skip rows that match an existing member."
        )
        update = options(analysis)["update"]
        self.assertEqual(
            (update["label"], update["enabled"], update["suggested"]), (f"Update {self.label} instead", True, False)
        )
        self.assertEqual(
            analysis.facts["why"],
            f"ada@example.com is the primary email of {self.label}, and the upload said to skip rows that match an "
            "existing member.",
        )

    def test_updating_instead_needs_permission(self):
        analysis = self.analyse_one(row("ada@example.com"), mode=SKIP_EXISTING, can_update=False)

        self.assertEqual(options(analysis)["update"]["reason"], NO_CHANGE_PERMISSION)

    def test_matched_by_member_uuid(self):
        analysis = self.analyse_one(uuid_row("ada@example.com", self.ada.pk), UUID_HEADERS, mode=SKIP_EXISTING)

        self.assertEqual(analysis.conflict, "exists_but_skip_mode")
        self.assertEqual(
            analysis.facts["why"],
            f"The Member UUID names {self.label}, and the upload said to skip rows that match an existing member.",
        )

    def test_new_members_are_still_ready_to_create(self):
        analysis = self.analyse_one(row("new@example.com"), mode=SKIP_EXISTING)

        self.assertEqual((analysis.status, analysis.default), ("ready_create", "create"))

    def test_skipped_by_default_or_updated_when_chosen(self):
        cells_row = row("ada@example.com", Organization="Engines")

        (skipped,) = self.apply([cells_row], mode=SKIP_EXISTING)
        self.ada.refresh_from_db()
        self.assertEqual((skipped.outcome, self.ada.organization), ("skipped", None))

        (updated,) = self.apply([cells_row], {2: ("update", [])}, mode=SKIP_EXISTING)
        self.ada.refresh_from_db()
        self.assertEqual((updated.outcome, self.ada.organization), ("updated", "Engines"))
