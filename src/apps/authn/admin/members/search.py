"""Admin search for members, contact emails and contact phones: exact matches first, phones only for phone numbers.

Django's stock search splits the term into words; every word must match, and a word may match any of the admin's
``search_fields`` (``icontains``). ``RankedSearchMixin`` adds two things on top:

* **Phone numbers.** ``ContactPhone.phone_number`` holds national digits only, so a typed number such as
  ``(209) 555-0100`` or ``+1 209 555 0100`` can only be found through its digits. They are searched when the *whole*
  term is phone-shaped (``phone_digits``): digits, spaces and ``( ) - . +``, with at least ``MIN_PHONE_DIGITS``
  digits. A term with a letter or an ``@`` is never a phone search. The member search used to strip the non-digits
  of *any* term and match what was left against phones, so ``jdoe32@example.edu`` also listed every member whose
  phone contains "32", and the member pickers (20 per page) filled up with those.
* **Exact matches first.** Unless a column sort was picked (``?o=``), results are ordered by ``search_rank`` ahead
  of the list's usual order: an address equal to the term (any letter case); then an address that starts with it,
  ``jdoe`` → ``jdoe@…`` (or a phone equal to its digits); then everything else. Every member picker
  (autocomplete) runs ``MemberAdmin.get_search_results`` too, so the member searched for comes first there as well.
"""

import re

from django.contrib.admin.utils import lookup_spawns_duplicates
from django.contrib.admin.views.main import ORDER_VAR
from django.db.models import Case, Exists, IntegerField, OuterRef, Value, When

from ...models import ContactEmail, ContactPhone

#: The fewest digits a phone-shaped term needs before phone numbers are searched ("555" still finds 555 numbers).
MIN_PHONE_DIGITS = 3

# Digits plus the characters people type inside a phone number. No letters and no "@", so an email address, a
# handle such as "jdoe28" or "Jane 209" is never a phone search.
PHONE_SHAPED_RE = re.compile(r"[0-9\s().+\-]+")
NON_DIGIT_RE = re.compile(r"[^0-9]")

# ``search_rank`` values, best first.
EXACT, CLOSE, OTHER = 0, 1, 2


def search_text(term) -> str:
    """The whole term without surrounding spaces or one pair of matching quotes (Django's phrase syntax)."""
    text = str(term or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def phone_digits(term) -> str:
    """The national digits to look for in phone numbers, or ``""`` when the term is not a phone number.

    Numbers are US only (``PHONE_REGION_CHOICES``) and stored without the country code, so the ``1`` of ``+1 …`` and
    of an 11-digit ``1XXXXXXXXXX`` is dropped. Any other leading ``1`` stays: ``1234`` is the end of a number.
    """
    text = search_text(term)
    if not PHONE_SHAPED_RE.fullmatch(text):
        return ""
    digits = NON_DIGIT_RE.sub("", text)
    if digits.startswith("1") and (text.startswith("+") or len(digits) == 11):
        digits = digits[1:]
    return digits if len(digits) >= MIN_PHONE_DIGITS else ""


def email_terms(term) -> tuple[str, str]:
    """``(exact, prefix)``: the address to match exactly, and how a close match starts (``""`` when none applies).

    A full or partial address (it has an ``@``) is matched exactly and as the start of an address. A single word
    without one is taken as the part before the ``@``: ``jdoe`` ranks ``jdoe@example.edu`` above
    ``jdoe2@example.edu``. Several words never match one address.
    """
    text = search_text(term)
    if not text or text.startswith("@") or any(char.isspace() for char in text):
        return "", ""
    if "@" in text:
        return text, text
    return "", f"{text}@"


def _rank(whens):
    return Case(*whens, default=Value(OTHER), output_field=IntegerField()) if whens else None


def member_search_rank(term):
    """Exact address, then an address starting with the term or a phone equal to its digits, then the rest."""
    exact, prefix = email_terms(term)
    digits = phone_digits(term)
    emails = ContactEmail.objects.filter(member=OuterRef("pk"))
    whens = []
    if exact:
        whens.append(When(Exists(emails.filter(email_address__iexact=exact)), then=Value(EXACT)))
    if prefix:
        whens.append(When(Exists(emails.filter(email_address__istartswith=prefix)), then=Value(CLOSE)))
    if digits:
        phones = ContactPhone.objects.filter(member=OuterRef("pk"), phone_number=digits)
        whens.append(When(Exists(phones), then=Value(CLOSE)))
    return _rank(whens)


def contact_email_search_rank(term):
    """The address equal to the term, then addresses starting with it, then the rest."""
    exact, prefix = email_terms(term)
    whens = []
    if exact:
        whens.append(When(email_address__iexact=exact, then=Value(EXACT)))
    if prefix:
        whens.append(When(email_address__istartswith=prefix, then=Value(CLOSE)))
    return _rank(whens)


def contact_phone_search_rank(term):
    """The number equal to the term's digits, then the rest."""
    digits = phone_digits(term)
    return _rank([When(phone_number=digits, then=Value(EXACT))] if digits else [])


def order_by_search_rank(request, queryset, rank):
    """Put ``rank`` ahead of the queryset's own order, unless the list is sorted by a column the user picked.

    ``alias`` rather than ``annotate``: the rank is only sorted on, so the changelist's ``count()`` (which drops the
    ordering) never computes it. With ``distinct()`` Django still selects the expression it orders by, as PostgreSQL
    requires.
    """
    if rank is None or (request is not None and request.GET.get(ORDER_VAR)):
        return queryset
    query = queryset.query
    current = query.order_by or (queryset.model._meta.ordering if query.default_ordering else ())
    return queryset.alias(search_rank=rank).order_by("search_rank", *current)


class RankedSearchMixin:
    """The stock admin search, plus phone digits for a phone-shaped term and the exact-first order.

    ``phone_search_field`` is the phone-number column to search (``None``: none); ``search_rank(term)`` returns the
    rank expression, or ``None`` when nothing can rank above the rest. Phone matches come from the same base queryset,
    so the list filters still apply.
    """

    phone_search_field = None

    def search_rank(self, term):
        return None

    def get_search_results(self, request, queryset, search_term):
        base = queryset
        queryset, may_have_duplicates = super().get_search_results(request, base, search_term)
        digits = phone_digits(search_term) if self.phone_search_field else ""
        if digits:
            queryset |= base.filter(**{f"{self.phone_search_field}__contains": digits})
            may_have_duplicates |= lookup_spawns_duplicates(self.opts, self.phone_search_field)
        return order_by_search_rank(request, queryset, self.search_rank(search_term)), may_have_duplicates
