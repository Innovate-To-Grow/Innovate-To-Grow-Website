"""R7 on an Admin account: the Admin lockout rules (``services/members/admins``) apply to an import's deactivations.

Nobody deactivates their own Admin account, and the last active Admin is never deactivated. The review disables such a
tick with the reason (for the Admin the analysis is for), and the apply checks every ticked deactivation together.
"""

from apps.authn.models import Member
from apps.authn.services.members.import_.review import save_choices
from apps.authn.tests.services.members.import_.apply.test_apply import ApplyTestCase
from apps.authn.tests.services.members.import_.helpers import row

OWN = "You cannot deactivate your own Admin account. Ask another Admin to do it."
LAST_ONE = "You cannot deactivate this Admin account: the site must keep at least one active Admin."
LAST_ALL = "You cannot deactivate these Admin accounts: the site must keep at least one active Admin."


class AdminLockoutTests(ApplyTestCase):
    """``self.admin`` (from ``ApplyTestCase``) is an active Admin; Ada is a regular member."""

    def setUp(self):
        super().setUp()
        self.sam = self.member("Sam", "Admin", "sam@example.com", is_staff=True)
        self.kim = self.member("Kim", "Admin", "kim@example.com", is_staff=True)
        self.rows = [
            row("sam@example.com", First_Name="Sam", Last_Name="Admin", Active="No"),
            row("kim@example.com", First_Name="Kim", Last_Name="Admin", Active="No"),
        ]

    def r7(self, analysis, member):
        return next(item for item in analysis.risky[str(member.pk)] if item["code"] == "R7")

    def tick_both(self, batch):
        posted = {2: ("update", [f"R7:{self.sam.pk}"]), 3: ("update", [f"R7:{self.kim.pk}"])}
        save_choices(batch, user=self.admin, version=0, posted=posted, command="save", bulk={})

    def test_your_own_admin_account_is_disabled_with_the_reason(self):
        analysis = self.analyse_one(self.rows[0], actor=self.sam)

        self.assertEqual((self.r7(analysis, self.sam)["enabled"], self.r7(analysis, self.sam)["reason"]), (False, OWN))

    def test_another_admin_or_a_regular_member_may_be_deactivated(self):
        admin_row = self.analyse_one(self.rows[0], actor=self.admin)
        member_row = self.analyse_one(row("ada@example.com", Active="No"), actor=self.admin)

        self.assertTrue(self.r7(admin_row, self.sam)["enabled"])
        self.assertTrue(self.r7(member_row, self.ada)["enabled"])

    def test_the_last_active_admin_is_disabled_with_the_reason(self):
        Member.objects.filter(pk__in=[self.admin.pk, self.kim.pk]).update(is_staff=False, is_superuser=False)

        analysis = self.analyse_one(self.rows[0])

        self.assertEqual(self.r7(analysis, self.sam)["reason"], LAST_ONE)

    def test_ticks_that_together_would_leave_no_admin_are_refused_at_the_apply(self):
        Member.objects.filter(pk=self.admin.pk).update(is_staff=False, is_superuser=False)
        batch = self.stage(self.rows, self.admin)
        self.tick_both(batch)

        result = self.confirm(batch)

        self.assertEqual((result.status, result.message), ("refused", LAST_ALL))
        self.assertEqual(batch.status, "review")
        self.assertEqual(Member.objects.filter(is_staff=True, is_active=True).count(), 2)

    def test_ticks_that_leave_an_admin_are_applied(self):
        batch = self.stage(self.rows, self.admin, actor=self.admin)
        self.tick_both(batch)

        result = self.confirm(batch, actor=self.admin)

        self.assertEqual(result.status, "applied")
        self.assertEqual(list(Member.objects.filter(is_staff=True, is_active=True)), [self.admin])
        self.assertEqual(batch.summary["risky"], {"active_changes": 2, "privileged_changes": 2})
