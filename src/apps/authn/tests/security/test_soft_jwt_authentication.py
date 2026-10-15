from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.authn.models import Member
from apps.authn.security import SoftJWTAuthentication
from apps.authn.tests.stale_bearer import stale_bearer_headers, valid_bearer_header

factory = APIRequestFactory()


class WhoAmIView(APIView):
    authentication_classes = [SoftJWTAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"member": str(request.user.pk) if request.user.is_authenticated else None})


class MembersOnlyView(WhoAmIView):
    permission_classes = [IsAuthenticated]


class SoftJWTAuthenticationTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.member = Member.objects.create_user(password="testpass123", is_active=True)

    @staticmethod
    def authenticate(header=None):
        extra = {"HTTP_AUTHORIZATION": header} if header is not None else {}
        return SoftJWTAuthentication().authenticate(Request(factory.get("/", **extra)))

    def test_valid_token_authenticates_the_member(self):
        user, token = self.authenticate(valid_bearer_header(self.member))

        self.assertEqual(user, self.member)
        self.assertEqual(token["member_uuid"], str(self.member.pk))

    def test_no_header_is_anonymous(self):
        self.assertIsNone(self.authenticate())

    def test_another_scheme_is_anonymous(self):
        self.assertIsNone(self.authenticate("Basic dXNlcjpwYXNz"))

    def test_every_stale_token_is_anonymous(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                self.assertIsNone(self.authenticate(header))

    def test_the_strict_class_rejects_what_the_soft_class_lets_through(self):
        # Guards the premise: every one of these headers is a 401 on a stock JWTAuthentication.
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                with self.assertRaises(AuthenticationFailed):
                    JWTAuthentication().authenticate(Request(factory.get("/", HTTP_AUTHORIZATION=header)))

    def test_a_real_fault_is_not_swallowed(self):
        with patch.object(JWTAuthentication, "authenticate", side_effect=DatabaseError("db is down")):
            with self.assertRaises(DatabaseError):
                self.authenticate(valid_bearer_header(self.member))

    def test_view_sees_the_member_behind_a_valid_token(self):
        response = WhoAmIView.as_view()(factory.get("/", HTTP_AUTHORIZATION=valid_bearer_header(self.member)))

        self.assertEqual(response.data, {"member": str(self.member.pk)})

    def test_view_sees_nobody_behind_a_stale_token(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                response = WhoAmIView.as_view()(factory.get("/", HTTP_AUTHORIZATION=header))

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, {"member": None})

    def test_it_cannot_authorize_anything_a_token_did_not(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(stale=label):
                response = MembersOnlyView.as_view()(factory.get("/", HTTP_AUTHORIZATION=header))

                self.assertEqual(response.status_code, 401)
