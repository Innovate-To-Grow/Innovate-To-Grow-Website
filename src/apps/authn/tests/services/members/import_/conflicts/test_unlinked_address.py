from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_.review.analysis.choices import NEEDS_NAMES, NO_CHANGE_PERMISSION, PRIVILEGED
from apps.authn.tests.services.members.import_.conflicts.test_conflicts_matched import (
    UUID_HEADERS,
    not_privileged,
    options,
    uuid_row,
)
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


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

    def test_create_claim_takes_the_verified_cell_but_never_re_subscribes(self):
        """The record may carry the person's opt-out: Subscribed TRUE can't turn it back on (no tick exists here)."""
        cells_row = row("loose@example.com", Primary_Verified="TRUE", Primary_Subscribed="TRUE", **self.lin)

        (outcome,) = self.apply([cells_row], {2: (self.claim, [])})

        self.loose.refresh_from_db()
        self.assertEqual((self.loose.verified, self.loose.subscribe), (True, False))
        self.assertIn(
            "Primary Subscribed is TRUE, but loose@example.com is unsubscribed; left unsubscribed (an import never "
            "re-subscribes an address; with the person's consent, re-subscribe it under Contact Emails)",
            outcome.notes,
        )
        self.assertIn(
            "Takes loose@example.com (a contact email with no member) as the primary email (verified, not subscribed)",
            outcome.changes,
        )

    def test_create_claim_of_a_subscribed_record_keeps_it_unless_the_cell_says_false(self):
        kept = ContactEmail.objects.create(member=None, email_address="kept@example.com", subscribe=True)
        dropped = ContactEmail.objects.create(member=None, email_address="dropped@example.com", subscribe=True)
        rows = [
            row("kept@example.com", First_Name="Kim", Last_Name="Kept"),
            row("dropped@example.com", First_Name="Dee", Last_Name="Dropped", Primary_Subscribed="FALSE"),
        ]

        self.apply(rows, {2: (f"create_claim:{kept.pk}", []), 3: (f"create_claim:{dropped.pk}", [])})

        kept.refresh_from_db()
        dropped.refresh_from_db()
        self.assertEqual((kept.email_type, kept.subscribe), ("primary", True))
        self.assertEqual((dropped.email_type, dropped.subscribe), ("primary", False))

    def test_attach_to_never_re_subscribes_the_record(self):
        cells_row = row("loose@example.com", Secondary_Email="ada@example.com", Primary_Subscribed="TRUE", **self.lin)

        (outcome,) = self.apply([cells_row], {2: (f"attach_to:{self.ada.pk}", [])})

        self.loose.refresh_from_db()
        self.assertEqual((self.loose.member, self.loose.subscribe), (self.ada, False))
        self.assertIn(
            "Primary Subscribed is TRUE, but loose@example.com is unsubscribed; left unsubscribed (an import never "
            "re-subscribes an address; with the person's consent, re-subscribe it under Contact Emails)",
            outcome.notes,
        )

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
