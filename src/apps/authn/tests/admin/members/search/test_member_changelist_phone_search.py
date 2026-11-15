import datetime

from django.test import override_settings

from apps.authn.tests.admin.members.search.test_member_admin_exact_search import (
    CHANGELIST,
    MEMBER_PICKERS,
    Member,
    _joined,
    _member,
    _SearchFixture,
)


class MemberChangelistPhoneSearchTests(_SearchFixture):
    """Phone searches that worked before keep working; only phone-shaped terms reach phone numbers."""

    def test_full_number_in_every_common_format_finds_the_member_first(self):
        for term in (
            "2097654100",
            "(209) 765-4100",
            "(209)765-4100",
            "209-765-4100",
            "209.765.4100",
            "209 765 4100",
            "+1 209 765 4100",
            "+1 (209) 765-4100",
            "+12097654100",
            "12097654100",
            "1-209-765-4100",
        ):
            with self.subTest(term=term):
                results = self.changelist(term)
                self.assertEqual(results[0], self.ana)
                self.assert_no_decoys(results)

    def test_partial_numbers_still_match(self):
        for term in ("7654100", "765-4100", "765 4100"):
            with self.subTest(term=term):
                self.assertIn(self.ana, self.changelist(term))

    def test_area_code_search_still_lists_every_matching_number(self):
        results = self.changelist("209", all_pages=True)
        self.assertIn(self.ana, results)
        self.assertLessEqual(set(self.decoys), set(results))

    def test_three_digits_are_enough_and_two_are_not(self):
        self.assertEqual(self.changelist("(765)"), [self.ana])
        self.assertEqual(self.changelist("(76)"), [])

    def test_formatted_partial_number_matches_only_numbers_containing_its_digits(self):
        results = self.changelist("(209) 32", all_pages=True)
        self.assertEqual(set(results), {decoy for index, decoy in enumerate(self.decoys) if index % 2 == 0})

    def test_name_with_digits_is_not_a_phone_search(self):
        results = self.changelist("Ana 209")
        self.assert_no_decoys(results)
        self.assertLessEqual(set(results), {self.ana})

    def test_two_words_match_name_parts(self):
        self.assertEqual(self.changelist("Ana Quill"), [self.ana])
        self.assertEqual(self.changelist("Fenwick Brian"), [self.brian])
        self.assertEqual(self.changelist("fenwick"), [self.bea, self.bob, self.brian])


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MemberChangelistActionsOnSearchResultsTests(_SearchFixture):
    """Select-all actions run on the ranked search results (annotated, de-duplicated) without errors."""

    def _post(self, action, term):
        return self.client.post(
            f"{CHANGELIST}?q={term}",
            {"action": action, "_selected_action": [str(self.brian.pk)], "select_across": "1", "index": "0"},
        )

    def test_vcard_export_of_all_search_results(self):
        response = self._post("export_members_to_vcard", "bfenwick28")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("FN:Brian Fenwick", body)
        self.assertIn("FN:Bea Fenwickson", body)
        self.assertEqual(body.count("BEGIN:VCARD"), 2)

    def test_deactivate_all_search_results(self):
        response = self._post("deactivate_members", "bfenwick28")
        self.assertEqual(response.status_code, 302)
        inactive = set(Member.objects.filter(is_active=False).values_list("pk", flat=True))
        self.assertEqual(inactive, {self.brian.pk, self.bea.pk})


class MemberPickerExactSearchTests(_SearchFixture):
    """Every member picker (autocomplete) runs the member search: the member is on the first page, first."""

    def test_exact_email_returns_only_that_member_in_every_picker(self):
        for app_label, model_name in MEMBER_PICKERS:
            with self.subTest(picker=model_name):
                self.assertEqual(
                    self.picker("aquill32@example.edu", app_label, model_name), ([str(self.ana.pk)], False)
                )

    def test_handle_returns_the_exact_handle_first_in_every_picker(self):
        for app_label, model_name in MEMBER_PICKERS:
            with self.subTest(picker=model_name):
                self.assertEqual(
                    self.picker("bfenwick28", app_label, model_name), ([str(self.brian.pk), str(self.bea.pk)], False)
                )

    def test_exact_handle_is_on_the_first_page_among_many_newer_partial_matches(self):
        for index in range(25):
            _member(
                "Bulk",
                "Fenwick",
                f"bfenwick28.{index}@example.net",
                joined=_joined(2025, 1) + datetime.timedelta(days=index),
            )
        ids, more = self.picker("bfenwick28")
        self.assertEqual(len(ids), 20)
        self.assertTrue(more)
        self.assertEqual(ids[0], str(self.brian.pk))

    def test_phone_number_finds_the_member_in_a_picker(self):
        for term in ("(209) 765-4100", "+1 209 765 4100", "2097654100"):
            with self.subTest(term=term):
                ids, _more = self.picker(term, "event", "eventregistration")
                self.assertEqual(ids[0], str(self.ana.pk))

    def test_full_name_in_a_picker(self):
        self.assertEqual(self.picker("Brian Fenwick", "authn", "contactphone"), ([str(self.brian.pk)], False))

    def test_empty_term_keeps_the_usual_newest_first_page(self):
        ids, more = self.picker("")
        self.assertTrue(more)
        expected = Member.objects.order_by("-date_joined").values_list("pk", flat=True)[:20]
        self.assertEqual(ids, [str(pk) for pk in expected])
