from apps.cms.models import CMSBlock, FooterContent
from apps.cms.tests.services.css_audit.test_audit_css_classes import _AuditCssClassesCase


class AuditCssClassesTests(_AuditCssClassesCase):
    def test_only_the_active_footer_is_scanned(self):
        FooterContent.objects.create(
            name="Old", slug="old", content={"contact_html": "<p class='shared only-old'>a</p>"}, is_active=False
        )
        FooterContent.objects.create(
            name="New", slug="new", content={"contact_html": "<p class=shared>b</p>"}, is_active=True
        )

        report = self._report()

        rows = {row["class_name"]: row for row in report["classes"]}
        self.assertEqual((rows["shared"]["usage_count"], rows["shared"]["footers"]), (1, ["footer:new"]))
        self.assertNotIn("only-old", rows)
        self.assertEqual(report["total_classes"], 3)

    def test_nested_html_fields_of_other_block_types_are_scanned(self):
        CMSBlock.objects.create(
            page=self.other_page,
            block_type="faq_list",
            sort_order=1,
            data={"items": [{"question": "Q", "answer_html": '<p class="faq-answer">A</p>'}]},
        )

        row = self._rows()["faq-answer"]

        self.assertEqual((row["pages"], row["block_types"], row["defined"]), (["/other"], ["faq_list"], False))
        self.assertEqual(row["sources"], ["block:faq_list"])

    def test_no_content_means_no_rows(self):
        CMSBlock.objects.all().delete()

        report = self._report()

        self.assertEqual((report["classes"], report["total_classes"], report["undefined_classes"]), ([], 0, 0))
