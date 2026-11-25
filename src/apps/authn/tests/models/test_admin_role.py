"""The single Admin role on ``Member``: the ``is_superuser`` mirror and the permission methods."""

from django.contrib.auth import get_user_model
from django.test import TestCase

Member = get_user_model()


def _member(**kw):
    return Member.objects.create_user(password="StrongPass123!", first_name="A", last_name="B", **kw)


def _stored_superuser(member) -> bool:
    return Member.objects.filter(pk=member.pk).values_list("is_superuser", flat=True).get()


class IsSuperuserMirrorTests(TestCase):
    def test_full_save_mirrors_is_staff(self):
        member = _member()
        member.is_staff = True
        member.save()
        self.assertTrue(_stored_superuser(member))

        member.is_staff = False
        member.save()
        self.assertFalse(_stored_superuser(member))

    def test_partial_save_of_is_staff_writes_the_mirror(self):
        member = _member()
        member.is_staff = True
        member.save(update_fields=["is_staff"])
        self.assertTrue(_stored_superuser(member))

        member.is_staff = False
        member.save(update_fields=["is_staff", "updated_at"])
        self.assertFalse(_stored_superuser(member))

    def test_partial_save_without_is_staff_leaves_the_stored_mirror_alone(self):
        """A save of unrelated columns never writes a value derived from a possibly stale in-memory ``is_staff``."""
        member = _member(is_staff=True)
        Member.objects.filter(pk=member.pk).update(is_superuser=False)
        member.first_name = "Renamed"
        member.save(update_fields=["first_name"])

        self.assertFalse(_stored_superuser(member))
        self.assertEqual(Member.objects.get(pk=member.pk).first_name, "Renamed")

    def test_partial_save_keeps_the_registration_pending_addition(self):
        member = _member(is_active=False, registration_pending=True)
        member.is_active = True
        member.is_staff = True
        member.save(update_fields=["is_active", "is_staff"])

        stored = Member.objects.get(pk=member.pk)
        self.assertFalse(stored.registration_pending)
        self.assertTrue(stored.is_superuser)

    def test_create_user_with_is_superuser_but_not_staff_is_not_an_admin(self):
        member = _member(is_superuser=True)
        self.assertFalse(member.is_superuser)
        self.assertFalse(_stored_superuser(member))

    def test_create_user_with_is_staff_is_a_full_admin(self):
        member = _member(is_staff=True)
        self.assertTrue(_stored_superuser(member))

    def test_create_superuser_is_an_admin(self):
        member = Member.objects.create_superuser(password="StrongPass123!", first_name="A", last_name="B")
        self.assertTrue(member.is_staff)
        self.assertTrue(_stored_superuser(member))


class AdminPermissionMethodTests(TestCase):
    def test_an_active_admin_has_every_permission(self):
        member = _member(is_staff=True)
        self.assertTrue(member.has_perm("authn.delete_member"))
        self.assertTrue(member.has_perm("cms.change_cmspage", obj=object()))
        self.assertTrue(member.has_perms(["authn.add_member", "event.view_event"]))
        self.assertTrue(member.has_module_perms("core"))

    def test_an_admin_with_a_stale_superuser_column_still_has_every_permission(self):
        member = _member(is_staff=True)
        Member.objects.filter(pk=member.pk).update(is_superuser=False)
        member.refresh_from_db()
        self.assertTrue(member.has_perm("authn.delete_member"))
        self.assertTrue(member.has_module_perms("authn"))

    def test_non_admins_have_no_permission(self):
        inactive_staff = _member(is_staff=True, is_active=False)
        regular = _member()
        superuser_row = _member()
        Member.objects.filter(pk=superuser_row.pk).update(is_superuser=True)
        superuser_row.refresh_from_db()
        self.assertTrue(superuser_row.is_superuser)

        for member in (inactive_staff, regular, superuser_row):
            with self.subTest(staff=member.is_staff, active=member.is_active, superuser=member.is_superuser):
                self.assertFalse(member.has_perm("authn.view_member"))
                self.assertFalse(member.has_perms(["authn.view_member"]))
                self.assertFalse(member.has_module_perms("authn"))
