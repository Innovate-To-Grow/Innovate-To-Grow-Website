import uuid

from django.core.exceptions import PermissionDenied
from django.test import TestCase, tag

from apps.authn.models import (
    AdminInvitation,
    ContactEmail,
    ContactPhone,
    EmailAuthChallenge,
    PhoneVerificationChallenge,
    RSAKeypair,
)
from apps.cli_admin.models import CliAccessToken, CliAuditLog, CliAuthorizationCode
from apps.core.models import BackgroundJob
from apps.core.services.db_tools.safe_orm import (
    DENIED_MODEL_LABELS,
    DENIED_WRITE_MODEL_LABELS,
    ActionRequestError,
    assert_snapshot_unchanged,
    check_model_permission,
    clone_model_instance,
    get_object,
    is_model_denied,
    record_repr,
    resolve_model,
    serialize_model_instance,
)
from apps.core.tests.services.platform.orm.test_safe_orm import Member
from apps.event.tests.helpers import make_admin, make_member
from apps.mail.models import EmailCampaign
from apps.projects.models import Semester
from apps.system_intelligence.models import SystemIntelligenceExport


@tag("safe_orm")
class WriteDenylistTests(TestCase):
    """Tables a proposed record write never touches. Contact rows (sign-in factors), verification challenges (proofs of
    a code), admin invitations (they make staff), the RSA sign-in key, the CLI audit log and background jobs can be
    read, never written; the CLI's sign-in codes and tokens and the assistant's exports can't be read either."""

    WRITE_DENIED = (
        AdminInvitation,
        BackgroundJob,
        CliAuditLog,
        ContactEmail,
        ContactPhone,
        EmailAuthChallenge,
        PhoneVerificationChallenge,
        RSAKeypair,
    )
    FULLY_DENIED = (CliAccessToken, CliAuthorizationCode, SystemIntelligenceExport)

    def test_each_model_is_listed_by_its_label(self):
        self.assertEqual(DENIED_WRITE_MODEL_LABELS, {model._meta.label_lower for model in self.WRITE_DENIED})
        self.assertLessEqual({model._meta.label_lower for model in self.FULLY_DENIED}, DENIED_MODEL_LABELS)

    def test_they_can_be_read_but_not_written(self):
        for model in self.WRITE_DENIED:
            label = f"{model._meta.app_label}.{model.__name__}"
            with self.subTest(model=label):
                self.assertFalse(is_model_denied(model, write=False))
                self.assertTrue(is_model_denied(model, write=True))
                self.assertIs(resolve_model(model._meta.app_label, model.__name__, write=False), model)
                with self.assertRaises(ActionRequestError) as error:
                    resolve_model(model._meta.app_label, model.__name__, write=True)
                self.assertEqual(str(error.exception), f"Write access is not allowed for {label}.")

    def test_cli_sign_in_and_exports_can_be_neither_read_nor_written(self):
        for model in self.FULLY_DENIED:
            for write in (False, True):
                with self.subTest(model=model.__name__, write=write):
                    self.assertTrue(is_model_denied(model, write=write))

    def test_many_to_many_tables_can_be_read_but_not_written(self):
        # Written directly, the Member.groups table would skip the "groups" field deny.
        for through in (Member.groups.through, EmailCampaign.selected_members.through):
            with self.subTest(model=through._meta.label):
                self.assertFalse(is_model_denied(through, write=False))
                self.assertTrue(is_model_denied(through, write=True))
                with self.assertRaises(ActionRequestError):
                    resolve_model(through._meta.app_label, through.__name__, write=True)

    def test_members_stay_writable(self):
        # The assistant's member updates (propose_member_update) write authn.Member; its own guard limits them.
        self.assertFalse(is_model_denied(Member, write=True))


@tag("safe_orm")
class RecordsTests(TestCase):
    def setUp(self):
        self.sem = Semester.objects.create(year=2030, season=1)

    def test_get_object_ok(self):
        self.assertEqual(get_object(Semester, str(self.sem.pk)), self.sem)

    def test_get_object_missing_raises(self):
        with self.assertRaises(ActionRequestError):
            get_object(Semester, str(uuid.uuid4()))

    def test_get_object_bad_pk_raises(self):
        with self.assertRaises(ActionRequestError):
            get_object(Semester, "not-a-uuid")

    def test_serialize_model_instance(self):
        data = serialize_model_instance(self.sem, write=False)
        self.assertIn("__repr__", data)
        self.assertIn("year", data)

    def test_record_repr_truncates(self):
        class Long:
            def __str__(self):
                return "x" * 400

        self.assertEqual(len(record_repr(Long())), 300)
        self.assertEqual(record_repr(self.sem), str(self.sem))

    def test_clone_model_instance(self):
        clone = clone_model_instance(self.sem)
        self.assertEqual(clone.pk, self.sem.pk)
        self.assertFalse(clone._state.adding)

    def test_check_model_permission(self):
        # Every Admin (an active staff member) is allowed; nobody else. See apps.core.utils.access.user_is_admin.
        for user in (None, make_member(email="np@example.com"), make_admin(email="gone@example.com", is_active=False)):
            with self.subTest(user=user), self.assertRaisesMessage(PermissionDenied, "Staff authentication"):
                check_model_permission(user, Semester, "change")
        check_model_permission(make_admin(email="pa@example.com"), Semester, "change")

    def test_assert_snapshot_unchanged(self):
        assert_snapshot_unchanged(None, {"a": 1}, "L")
        assert_snapshot_unchanged({"a": 1}, {"a": 1}, "L")
        with self.assertRaises(ActionRequestError):
            assert_snapshot_unchanged({"a": 1}, {"a": 2}, "L")
