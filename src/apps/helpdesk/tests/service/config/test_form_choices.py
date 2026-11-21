"""What the configuration forms offer.

- A category's default group and a response template's category are chosen among active ones, plus the one the row
  already has (so an unrelated save keeps a group or category switched off since); an inactive one is not chosen anew.
- A group's members and manager are chosen among staff with the Helpdesk app, plus whoever the group already has:
  someone who lost the app stays listed, marked "(no Helpdesk access)", so saving the group keeps them. Anyone else
  without the app is refused.
- None of these fields offers the related-object buttons (add, change, delete, view): groups, categories and members
  are set up on their own pages. A form asked for other fields only is built without them."""

from django.contrib import admin
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ....models import AssignmentGroup, ResponseTemplate, TicketCategory
from ...helpers import helpdesk_staff, make_admin, make_superuser

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

    def test_a_category_offers_active_groups_plus_its_own(self):
        parking = TicketCategory.objects.create(name="Parking", default_group=self.retired)

        _page, add = self.page("ticketcategory")
        _page, change = self.page("ticketcategory", parking)

        self.assertEqual(list(add.fields["default_group"].queryset), [self.events])
        self.assertEqual(set(change.fields["default_group"].queryset), {self.events, self.retired})

    def test_a_category_saves_with_its_inactive_group_but_cannot_take_one_anew(self):
        parking = TicketCategory.objects.create(name="Parking", default_group=self.retired)
        data = {"name": "Parking", "default_group": str(self.retired.pk), "is_active": "on", "order": "2"}

        kept = self.client.post(reverse("admin:helpdesk_ticketcategory_change", args=[parking.pk]), data)
        taken = self.client.post(reverse("admin:helpdesk_ticketcategory_add"), {**data, "name": "Showcase"})

        self.assertEqual(kept.status_code, 302)
        parking.refresh_from_db()
        self.assertEqual((parking.default_group, parking.order), (self.retired, 2))
        self.assertEqual(taken.status_code, 200)
        self.assertIn("default_group", taken.context["adminform"].form.errors)
        self.assertFalse(TicketCategory.objects.filter(name="Showcase").exists())

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
        group = AssignmentGroup.objects.create(name="Technical", manager=self.agent)
        pages = {
            ("ticketcategory", None): ("default_group",),
            ("responsetemplate", None): ("category",),
            ("assignmentgroup", None): ("members", "manager"),
            ("assignmentgroup", group): ("members", "manager"),
        }
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
        for model in (AssignmentGroup, TicketCategory, ResponseTemplate):
            with self.subTest(model.__name__):
                form = admin.site._registry[model].get_form(request, None, fields=["name"])

                self.assertEqual(list(form.base_fields), ["name"])


class GroupPeopleTests(_ChoicesCase):
    def setUp(self):
        super().setUp()
        self.master = make_superuser(email="master@example.com")
        # Still in the group (and its manager), without the Helpdesk app: it was taken away, or never given.
        self.former = make_admin(apps=["mail"], email="fran@example.com", first_name="Fran", last_name="Former")
        self.outsider = make_admin(apps=["mail"], email="oli@example.com", first_name="Oli", last_name="Outsider")
        self.group = AssignmentGroup.objects.create(name="Events", manager=self.former)
        self.group.members.add(self.agent, self.former)
        self.url = reverse("admin:helpdesk_assignmentgroup_change", args=[self.group.pk])

    def data(self, *members, **values) -> dict:
        people = members or (self.agent, self.former)
        return {
            "name": "Events",
            "description": "Showcase questions",
            "members": [str(member.pk) for member in people],
            "manager": str(self.former.pk),
            "is_active": "on",
            "order": "0",
            **values,
        }

    def test_helpdesk_staff_and_the_groups_own_people_are_offered_and_marked(self):
        page, form = self.page("assignmentgroup", self.group)

        for name in ("members", "manager"):
            with self.subTest(name):
                field = form.fields[name]
                self.assertEqual(set(field.queryset), {self.agent, self.master, self.former})
                self.assertEqual(field.label_from_instance(self.agent), "Avery Agent")
                self.assertEqual(field.label_from_instance(self.former), "Fran Former (no Helpdesk access)")
        self.assertContains(page, "Fran Former (no Helpdesk access)")
        self.assertNotContains(page, "Oli Outsider")

    def test_a_new_group_offers_helpdesk_staff_only(self):
        _page, form = self.page("assignmentgroup")

        self.assertEqual(set(form.fields["manager"].queryset), {self.agent, self.master})

    def test_saving_the_group_keeps_them(self):
        response = self.client.post(self.url, self.data())

        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(set(self.group.members.all()), {self.agent, self.former})
        self.assertEqual((self.group.manager, self.group.description), (self.former, "Showcase questions"))

    def test_someone_else_without_the_helpdesk_app_is_refused(self):
        as_member = self.client.post(self.url, self.data(self.agent, self.former, self.outsider))
        as_manager = self.client.post(self.url, self.data(manager=str(self.outsider.pk)))

        for response, field in ((as_member, "members"), (as_manager, "manager")):
            with self.subTest(field):
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["adminform"].form.errors)
        self.group.refresh_from_db()
        self.assertEqual((set(self.group.members.all()), self.group.manager), ({self.agent, self.former}, self.former))
