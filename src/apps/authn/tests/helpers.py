"""
Test helpers for creating members with ContactEmail records.
"""

import base64

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.authn.models import ContactEmail, Member

# A real 1x1 PNG. Profile-image uploads are checked against magic bytes on both the admin and the API
# path (apps.authn.services.members.profile_image), so placeholder payloads like b"new-image" are
# rejected — tests that upload an avatar need actual image bytes.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
PNG_1PX_DATA_URI = f"data:image/png;base64,{base64.b64encode(PNG_1PX).decode()}"


def png_upload(name="avatar.png"):
    """A valid PNG upload for profile-image tests."""
    return SimpleUploadedFile(name, PNG_1PX, content_type="image/png")


def scrape_admin_form(client, url, overrides=None, submit="_save"):
    """GET an admin change page and return its fields as a POST-ready dict.

    Admin change forms carry management forms, hidden ``initial-*`` inputs and readonly fields that a
    hand-written payload gets wrong (a missing key silently re-renders the form with errors instead of
    saving), so scrape what the page actually rendered.
    """
    from html.parser import HTMLParser

    response = client.get(url)
    fields: dict[str, str] = {}
    state = {"textarea": None, "select": None, "selected": None}

    class _FormParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attr = dict(attrs)
            name = attr.get("name")
            if tag == "input" and name:
                if attr.get("type") == "checkbox":
                    if "checked" in attr:
                        fields[name] = attr.get("value", "on")
                elif attr.get("type") != "file":
                    fields.setdefault(name, attr.get("value", ""))
            elif tag == "textarea" and name:
                state["textarea"] = name
            elif tag == "select" and name:
                state["select"] = name
            elif tag == "option" and state["select"] and "selected" in attr:
                state["selected"] = attr.get("value", "")

        def handle_data(self, data):
            if state["textarea"]:
                fields.setdefault(state["textarea"], data.strip())

        def handle_endtag(self, tag):
            if tag == "textarea":
                state["textarea"] = None
            elif tag == "select" and state["select"]:
                if state["selected"] is not None:
                    fields.setdefault(state["select"], state["selected"])
                state["select"] = None
                state["selected"] = None

    _FormParser().feed(response.content.decode())

    if overrides:
        fields.update(overrides)
    for key in ("_addanother", "_continue", "_save"):
        fields.pop(key, None)
    if submit:
        fields[submit] = "1"
    return fields


def create_test_member(email, password="testpass123", **kwargs):
    """
    Create a Member with a primary ContactEmail record.
    Member.email is left blank; the email is stored in ContactEmail.
    """
    member = Member.objects.create_user(
        password=password,
        **kwargs,
    )
    ContactEmail.objects.create(
        member=member,
        email_address=email,
        email_type="primary",
        verified=True,
    )
    # Store the email on the instance for convenience in tests
    member._test_email = email
    return member
