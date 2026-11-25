"""A deactivated account is never an Admin, so reactivating it never brings back a full Admin unasked."""

from django.test import TestCase

from apps.authn.models import Member


def _admin():
    return Member.objects.create_user(password="StrongPass123!", is_staff=True, is_active=True)


class DeactivationRemovesAdminTests(TestCase):
    def _stored(self, member):
        return Member.objects.values("is_active", "is_staff", "is_superuser").get(pk=member.pk)

    def test_full_save_of_a_deactivated_admin_removes_admin(self):
        member = _admin()
        member.is_active = False
        member.save()

        self.assertEqual(self._stored(member), {"is_active": False, "is_staff": False, "is_superuser": False})

    def test_partial_save_of_is_active_writes_the_demotion(self):
        member = _admin()
        member.is_active = False
        member.save(update_fields=["is_active", "updated_at"])

        self.assertEqual(self._stored(member), {"is_active": False, "is_staff": False, "is_superuser": False})

    def test_reactivating_does_not_restore_admin(self):
        member = _admin()
        member.is_active = False
        member.save(update_fields=["is_active"])
        member.refresh_from_db()

        member.is_active = True
        member.save(update_fields=["is_active"])

        self.assertEqual(self._stored(member), {"is_active": True, "is_staff": False, "is_superuser": False})

    def test_an_inactive_account_cannot_be_made_an_admin(self):
        member = Member.objects.create_user(password="StrongPass123!", is_active=False)
        member.is_staff = True
        member.save()

        self.assertEqual(self._stored(member), {"is_active": False, "is_staff": False, "is_superuser": False})

    def test_a_partial_save_of_another_column_leaves_the_stored_flags_alone(self):
        member = _admin()
        member.is_active = False  # in memory only: not written by this save
        member.save(update_fields=["first_name"])

        self.assertEqual(self._stored(member), {"is_active": True, "is_staff": True, "is_superuser": True})


class StaleInactiveAdminTests(TestCase):
    """An older release deactivated without removing Admin; reactivating such a row never restores Admin."""

    def _stale(self):
        member = _admin()
        Member.objects.filter(pk=member.pk).update(is_active=False)  # what the older release wrote
        return Member.objects.get(pk=member.pk)

    def _stored(self, member):
        return Member.objects.values("is_active", "is_staff", "is_superuser").get(pk=member.pk)

    def test_reactivating_by_full_or_partial_save_does_not_restore_admin(self):
        for update_fields in (None, ["is_active"]):
            with self.subTest(update_fields=update_fields):
                member = self._stale()
                member.is_active = True
                member.save(update_fields=update_fields)

                self.assertEqual(self._stored(member), {"is_active": True, "is_staff": False, "is_superuser": False})

    def test_an_unrelated_partial_save_writes_the_demotion_before_a_later_reactivation(self):
        member = self._stale()
        member.first_name = "Renamed"
        member.save(update_fields=["first_name"])
        member.is_active = True
        member.save(update_fields=["is_active"])

        self.assertEqual(self._stored(member), {"is_active": True, "is_staff": False, "is_superuser": False})

    def test_granting_admin_while_reactivating_a_regular_member_still_works(self):
        member = Member.objects.create_user(password="StrongPass123!", is_active=False)
        member = Member.objects.get(pk=member.pk)
        member.is_active = True
        member.is_staff = True
        member.save()

        self.assertEqual(self._stored(member), {"is_active": True, "is_staff": True, "is_superuser": True})
