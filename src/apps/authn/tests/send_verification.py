"""Test helpers that mint a real ALTCHA proof for protected send endpoints."""

from __future__ import annotations

import json
import re
import uuid
from functools import wraps

from django.conf import settings
from django.test.client import Client
from rest_framework.test import APIClient

from apps.authn.services.send_verification.constants import (
    FIELD_CHALLENGE_ID,
    FIELD_PAYLOAD,
    FIELD_REQUEST_ID,
    OP_ADMIN_LOGIN_REMEMBERED_CODE,
    OP_ADMIN_LOGIN_REQUEST_CODE,
    OP_ADMIN_LOGIN_RESEND,
    OP_CHANGE_PASSWORD_REQUEST_CODE,
    OP_CONTACT_EMAIL_CREATE,
    OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
    OP_CONTACT_PHONE_REQUEST_VERIFICATION,
    OP_DELETE_ACCOUNT_REQUEST_CODE,
    OP_EMAIL_AUTH_REQUEST_CODE,
    OP_EVENT_SEND_PHONE_CODE,
    OP_LOGIN_REQUEST_CODE,
    OP_PASSWORD_RESET_REQUEST_CODE,
    OP_PHONE_AUTH_REQUEST_CODE,
    OP_REGISTER,
    OP_REGISTER_RESEND_CODE,
)

CHALLENGE_PATH = "/authn/send-verification/challenge/"
_CONTACT_EMAIL_VERIFY = re.compile(r"^/authn/contact-emails/([^/]+)/request-verification/?$")
_CONTACT_PHONE_VERIFY = re.compile(r"^/authn/contact-phones/([^/]+)/request-verification/?$")


def _operation_for(path: str, data: dict) -> str | None:
    path = str(path).split("?", 1)[0]
    if path.rstrip("/") == "/authn/email-auth/request-code":
        return OP_EMAIL_AUTH_REQUEST_CODE
    if path.rstrip("/") == "/authn/phone-auth/request-code":
        return OP_PHONE_AUTH_REQUEST_CODE
    if path.rstrip("/") == "/authn/login/request-code":
        return OP_LOGIN_REQUEST_CODE
    if path.rstrip("/") == "/authn/register":
        return OP_REGISTER
    if path.rstrip("/") == "/authn/register/resend-code":
        return OP_REGISTER_RESEND_CODE
    if path.rstrip("/") == "/authn/password-reset/request-code":
        return OP_PASSWORD_RESET_REQUEST_CODE
    if path.rstrip("/") == "/authn/change-password/request-code":
        return OP_CHANGE_PASSWORD_REQUEST_CODE
    if path.rstrip("/") == "/authn/delete-account/request-code":
        return OP_DELETE_ACCOUNT_REQUEST_CODE
    if path.rstrip("/") == "/authn/contact-emails":
        return OP_CONTACT_EMAIL_CREATE
    if path.rstrip("/") == "/event/send-phone-code":
        return OP_EVENT_SEND_PHONE_CODE
    if path.rstrip("/") == "/admin/login":
        action = str(data.get("action") or "")
        if action == "remembered_code":
            return OP_ADMIN_LOGIN_REMEMBERED_CODE
        if action == "resend":
            return OP_ADMIN_LOGIN_RESEND
        if data.get("mode") == "password" or data.get("code"):
            return None
        if data.get("email") or action == "":
            return OP_ADMIN_LOGIN_REQUEST_CODE
        return None
    match = _CONTACT_EMAIL_VERIFY.match(path)
    if match:
        return OP_CONTACT_EMAIL_REQUEST_VERIFICATION
    match = _CONTACT_PHONE_VERIFY.match(path)
    if match:
        return OP_CONTACT_PHONE_REQUEST_VERIFICATION
    return None


def mint_send_verification(client: APIClient, operation: str, data: dict | None = None) -> dict:
    from altcha import Payload, solve_challenge
    from altcha.v2 import Challenge

    payload = dict(data or {})
    payload["operation"] = operation
    challenge_path = "/admin/send-verification/challenge/" if operation.startswith("admin.") else CHALLENGE_PATH
    if isinstance(client, APIClient):
        response = _original_api_post(client, challenge_path, payload, format="json")
        body = response.data
    else:
        response = _original_django_post(
            client,
            challenge_path,
            data=json.dumps(payload),
            content_type="application/json",
        )
        body = response.json()
    if response.status_code != 200:
        raise AssertionError(f"Challenge issuance failed: {response.status_code} {body}")
    challenge = Challenge.from_dict(body["challenge"])
    solution = solve_challenge(challenge)
    if solution is None:
        raise AssertionError("Unable to solve test ALTCHA challenge")
    return {
        FIELD_CHALLENGE_ID: body["challenge_id"],
        FIELD_PAYLOAD: Payload(challenge, solution).to_base64(),
        FIELD_REQUEST_ID: str(uuid.uuid4()),
    }


def _merge(data, extra):
    if data is None:
        return extra
    if hasattr(data, "copy") and not isinstance(data, dict):
        merged = data.copy()
        merged.update(extra)
        return merged
    merged = dict(data)
    merged.update(extra)
    return merged


_original_api_post = APIClient.post
_original_django_post = Client.post
_installed = False


def _maybe_attach(self, original, path, data, kwargs):
    if not getattr(settings, "SEND_VERIFICATION_TEST_AUTOSOLVE", False):
        return None
    if getattr(self, "_send_verification_busy", False):
        return None
    path_str = str(path)
    if path_str.rstrip("/").endswith("/send-verification/challenge"):
        return None
    payload = data if isinstance(data, dict) else dict(data or {})
    if payload.get(FIELD_CHALLENGE_ID):
        return None
    operation = _operation_for(path_str, payload)
    if not operation:
        return None
    self._send_verification_busy = True
    self._send_verification_path = path_str
    if operation == OP_CONTACT_EMAIL_REQUEST_VERIFICATION:
        match = _CONTACT_EMAIL_VERIFY.match(path_str)
        if match:
            payload["contact_id"] = match.group(1)
    if operation == OP_CONTACT_PHONE_REQUEST_VERIFICATION:
        match = _CONTACT_PHONE_VERIFY.match(path_str)
        if match:
            payload["contact_id"] = match.group(1)
    try:
        proof = mint_send_verification(self, operation, payload)
    except AssertionError:
        return None
    finally:
        self._send_verification_busy = False
    return _merge(data, proof)


def install_auto_verification() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    @wraps(_original_api_post)
    def auto_api_post(self, path, data=None, format=None, content_type=None, **extra):
        merged = _maybe_attach(self, _original_api_post, path, data, extra)
        if merged is not None:
            data = merged
            if format is None and content_type is None and isinstance(data, dict):
                format = "json"
        return _original_api_post(self, path, data=data, format=format, content_type=content_type, **extra)

    @wraps(_original_django_post)
    def auto_django_post(self, path, data=None, content_type=None, **extra):
        merged = _maybe_attach(self, _original_django_post, path, data, extra)
        if merged is not None:
            data = merged
        if content_type is None:
            return _original_django_post(self, path, data=data, **extra)
        return _original_django_post(self, path, data=data, content_type=content_type, **extra)

    APIClient.post = auto_api_post
    Client.post = auto_django_post
