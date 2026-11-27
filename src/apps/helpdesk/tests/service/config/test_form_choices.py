"""What the configuration forms offer.

- A response template's category is chosen among active ones, plus the one the row already has (so an unrelated save
  keeps a category switched off since); an inactive one is not chosen anew.
- A category no longer offers a default group (tickets have no owner, I2G-HELPDESK-01): saving it keeps the
  deprecated value it has.
- Assignment groups have no admin page any more.
- The category field offers no related-object buttons (add, change, delete, view): categories are set up on their own
  page. A form asked for other fields only is built without them."""

from django.contrib import admin
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ....models import AssignmentGroup, ResponseTemplate, TicketCategory
from ...helpers import helpdesk_staff

RELATED_FLAGS = ("can_add_related", "can_change_related", "can_delete_related", "can_view_related")


class _ChoicesCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)

    def page(self, name: str, obj=None):
        url = reverse(f"admin:helpdesk_{name}_change", args=[obj.pk]) if obj else reverse(f"admin:helpdesk_{name}_add")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response, response.context["adminform"].form


class ActiveChoiceTests(_ChoicesCase):
    def setUp(self):
        super().setUp()
        self.events = AssignmentGroup.objects.create(name="Events")
        self.retired = AssignmentGroup.objects.create(name="Retired", is_active=False)
        self.registration = TicketCategory.objects.create(name="Registration")
        self.old = TicketCategory.objects.create(name="Old", is_active=False)

    def test_a_category_offers_no_group_and_keeps_its_deprecated_one(self):
        parking = TicketCategory.objects.create(name="Parking", default_group=self.retired)
        data = {"name": "Parking", "default_group": str(self.events.pk), "is_active": "on", "order": "2"}

        _page, add = self.page("ticketcategory")
        kept = self.client.post(reverse("admin:helpdesk_ticketcategory_change", args=[parking.pk]), data)

        self.assertNotIn("default_group", add.fields)
        self.assertEqual(kept.status_code, 302)
        parking.refresh_from_db()
        self.assertEqual((parking.default_group, parking.order), (self.retired, 2))

    def test_assignment_groups_have_no_page(self):
        self.assertNotIn(AssignmentGroup, admin.site._registry)
        self.assertEqual(self.client.get("/admin/helpdesk/assignmentgroup/").status_code, 404)

    def test_a_template_offers_active_categories_plus_its_own(self):
        template = ResponseTemplate.objects.create(name="Old answer", body="Hello", category=self.old)

        _page, add = self.page("responsetemplate")
        _page, change = self.page("responsetemplate", template)
        saved = self.client.post(
            reverse("admin:helpdesk_responsetemplate_change", args=[template.pk]),
            {
                "name": "Old answer",
                "body": "Hello again",
                "category": str(self.old.pk),
                "is_active": "on",
                "order": "0",
            },
        )

        self.assertEqual(list(add.fields["category"].queryset), [self.registration])
        self.assertEqual(set(change.fields["category"].queryset), {self.registration, self.old})
        self.assertEqual(saved.status_code, 302)
        template.refresh_from_db()
        self.assertEqual((template.category, template.body), (self.old, "Hello again"))

    def test_no_related_object_buttons(self):
        template = ResponseTemplate.objects.create(name="Answer", body="Hello")
        pages = {("responsetemplate", None): ("category",), ("responsetemplate", template): ("category",)}
        for (name, obj), fields in pages.items():
            with self.subTest(name, change=obj is not None):
                page, form = self.page(name, obj)
                for field in fields:
                    widget = form.fields[field].widget
                    self.assertEqual(
                        {flag: getattr(widget, flag) for flag in RELATED_FLAGS}, dict.fromkeys(RELATED_FLAGS, False)
                    )
                self.assertNotContains(page, "related-widget-wrapper-link")

    def test_a_form_asked_for_other_fields_only_is_left_as_asked(self):
        request = RequestFactory().get("/admin/")
        request.user = self.agent
        for model in (TicketCategory, ResponseTemplate):
            with self.subTest(model.__name__):
                form = admin.site._registry[model].get_form(request, None, fields=["name"])

                self.assertEqual(list(form.base_fields), ["name"])
