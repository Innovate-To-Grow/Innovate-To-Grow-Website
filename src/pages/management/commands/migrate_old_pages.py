"""
Migrate old Flask/Jinja2 HTML templates into the new CMS as Page objects.

Reads templates from the old site at OLD_TEMPLATES_ROOT, extracts the
{% block content %} section (or full file if no content block exists),
strips all Jinja2 syntax, and creates published Page records.

All pages are created under the 'legacy/' slug prefix to avoid conflicts
with new system routes and to match the existing seed_initial_data menu structure.

Safe to run multiple times — uses update_or_create on slug.
"""

import os
import re

from django.core.management.base import BaseCommand
from django.utils import timezone

from pages.models import HomePage, Page

OLD_TEMPLATES_ROOT = "C:/_py/Innovate-To-Grow-Website-Old/project/templates"

# (relative_path_from_templates_root, slug, title)
PAGES_MAP = [
    # ── Error pages ──────────────────────────────────────────────────────────
    ("404.html", "legacy/errors/404", "404 Not Found"),
    ("429.html", "legacy/errors/429", "429 Too Many Requests"),
    # ── Admin pages ───────────────────────────────────────────────────────────
    ("admin/index.html", "legacy/admin/index", "Admin Dashboard"),
    ("admin/login_form.html", "legacy/admin/login", "Admin Login"),
    ("admin/user_list.html", "legacy/admin/users", "Admin User List"),
    ("admin/contact.html", "legacy/admin/contact", "Admin Contact"),
    ("admin/documentation.html", "legacy/admin/documentation", "Admin Documentation"),
    ("admin/edit_form_create.html", "legacy/admin/edit-form-create", "Admin Edit Form (Create)"),
    ("admin/edit_form_edit.html", "legacy/admin/edit-form-edit", "Admin Edit Form (Edit)"),
    ("admin/edit_form_list.html", "legacy/admin/edit-form-list", "Admin Edit Form (List)"),
    ("admin/event_create.html", "legacy/admin/event-create", "Admin Event Create"),
    ("admin/event_edit.html", "legacy/admin/event-edit", "Admin Event Edit"),
    ("admin/manual_email.html", "legacy/admin/manual-email", "Admin Manual Email"),
    ("admin/new_admin_email.html", "legacy/admin/new-admin-email", "Admin New Admin Email"),
    ("admin/new_admin_form.html", "legacy/admin/new-admin-form", "Admin New Admin Form"),
    ("admin/preview_form.html", "legacy/admin/preview-form", "Admin Preview Form"),
    ("admin/prospects.html", "legacy/admin/prospects", "Admin Prospects"),
    ("admin/register_admin_form.html", "legacy/admin/register-admin", "Admin Register"),
    ("admin/bounce_email.html", "legacy/admin/bounce-email", "Admin Bounce Email"),
    ("admin/catch_bounces.html", "legacy/admin/catch-bounces", "Admin Catch Bounces"),
    # ── Geo ───────────────────────────────────────────────────────────────────
    ("geo/geo.html", "legacy/geo", "Geo / Map"),
    # ── Home page state variants ───────────────────────────────────────────────
    ("home/home-pre-event.html", "legacy/home/pre-event", "Home (Pre-Event)"),
    ("home/home-during-event.html", "legacy/home/during-event", "Home (During Event)"),
    ("home/home-post-event.html", "legacy/home/post-event", "Home (Post-Event)"),
    ("home/home-during-semester.html", "legacy/home/during-semester", "Home (During Semester)"),
    # ── Home base template + email ────────────────────────────────────────────
    ("home/template.html", "legacy/home/base-template", "Home Base Template"),
    ("home/template-email-team-students.html", "legacy/home/email-team-students", "Email: Team Students"),
    # ── About / program pages ─────────────────────────────────────────────────
    ("home/about.html", "legacy/about", "About Innovate To Grow"),
    ("home/about_EngSL.html", "legacy/about/engineering-service-learning", "Engineering Service Learning"),
    ("home/engineering-capstone.html", "legacy/engineering-capstone", "Engineering Capstone"),
    ("home/software-capstone.html", "legacy/software-capstone", "Software Engineering Capstone"),
    # ── Event info pages ──────────────────────────────────────────────────────
    ("home/event.html", "legacy/event", "Event"),
    ("home/schedule.html", "legacy/event/schedule", "Event Schedule"),
    ("home/projects-teams.html", "legacy/event/projects-teams", "Projects & Teams"),
    ("home/judges.html", "legacy/event/judges", "For Judges"),
    ("home/attendees.html", "legacy/event/attendees", "For Attendees"),
    ("home/students.html", "legacy/students", "For Students"),
    ("home/acknowledgement.html", "legacy/event/acknowledgement", "Partners & Sponsors Acknowledgement"),
    ("home/judging.html", "legacy/event/judging", "Judging Guidelines"),
    # ── Past events hub + archives ────────────────────────────────────────────
    ("home/past-events.html", "legacy/event/past", "Past Events"),
    ("home/2014-sponsors.html", "legacy/events/2014-sponsors", "2014 Sponsors"),
    ("home/2015-sponsors.html", "legacy/events/2015-sponsors", "2015 Sponsors"),
    ("home/2020-fall-post-event.html", "legacy/events/2020-fall", "Fall 2020 Event"),
    ("home/2021-spring-event.html", "legacy/events/2021-spring", "Spring 2021 Event"),
    ("home/2021-fall-event.html", "legacy/events/2021-fall", "Fall 2021 Event"),
    ("home/2022-spring-event.html", "legacy/events/2022-spring", "Spring 2022 Event"),
    ("home/2022-fall-event.html", "legacy/events/2022-fall", "Fall 2022 Event"),
    ("home/2023-spring-event.html", "legacy/events/2023-spring", "Spring 2023 Event"),
    ("home/2023-fall-event.html", "legacy/events/2023-fall", "Fall 2023 Event"),
    ("home/2024-spring-event.html", "legacy/events/2024-spring", "Spring 2024 Event"),
    ("home/2024-fall-event.html", "legacy/events/2024-fall", "Fall 2024 Event"),
    ("home/2025-spring-event.html", "legacy/events/2025-spring", "Spring 2025 Event"),
    ("home/2025-fall-event.html", "legacy/events/2025-fall", "Fall 2025 Event"),
    # ── Projects pages ────────────────────────────────────────────────────────
    ("home/projects.html", "legacy/projects", "Projects"),
    ("home/current-projects.html", "legacy/projects/current", "Current Projects"),
    ("home/past-projects.html", "legacy/projects/past", "Past Projects"),
    ("home/project-submission.html", "legacy/projects/submit", "Submit a Project"),
    ("home/sample-proposals.html", "legacy/projects/sample-proposals", "Sample Project Proposals"),
    # ── Partnership / sponsorship ─────────────────────────────────────────────
    ("home/partnership.html", "legacy/partnership", "Partner with Us"),
    ("home/sponsorship.html", "legacy/partnership/sponsorship", "Sponsorship"),
    ("home/faq.html", "legacy/partnership/faq", "FAQs"),
    ("home/contact-us.html", "legacy/contact-us", "Contact Us"),
    # ── Student resources ─────────────────────────────────────────────────────
    ("home/i2g-students-preparation.html", "legacy/students/event-preparation", "Event Preparation for Students"),
    ("home/I2G-student-agreement.html", "legacy/students/agreement", "Student Agreement"),
    ("home/I2G-project-sponsor-acknowledgement.html", "legacy/students/sponsor-acknowledgement", "Project Sponsor Acknowledgement"),
    ("home/ferpa.html", "legacy/students/ferpa", "FERPA Agreement"),
    ("home/video-preparation.html", "legacy/students/video-preparation", "Video Preparation"),
    ("home/capstone-purchasing-reimbursement.html", "legacy/students/purchasing-reimbursement", "Purchasing & Reimbursement"),
    # ── Legal ─────────────────────────────────────────────────────────────────
    ("home/terms_and_conditions.html", "legacy/terms", "Terms & Conditions"),
    # ── Template includes (nav, footer, etc.) ─────────────────────────────────
    ("includes/footer.html", "legacy/includes/footer", "Footer (Legacy Include)"),
    ("includes/nav.html", "legacy/includes/nav", "Navigation (Legacy Include)"),
    ("includes/scripts.html", "legacy/includes/scripts", "Scripts (Legacy Include)"),
    ("includes/styles.html", "legacy/includes/styles", "Styles (Legacy Include)"),
    # ── Membership: events flow ───────────────────────────────────────────────
    ("membership/events/event_enter_form.html", "legacy/membership/events/enter", "Event Registration: Enter Email"),
    ("membership/events/event_registration.html", "legacy/membership/events/registration", "Event Registration Form"),
    ("membership/events/event_instructions_sent.html", "legacy/membership/events/instructions-sent", "Event Registration: Instructions Sent"),
    ("membership/events/otp.html", "legacy/membership/events/otp", "Event Registration: OTP Verification"),
    ("membership/events/successfully_registered.html", "legacy/membership/events/success", "Event Registration: Success"),
    ("membership/events/no_live_event.html", "legacy/membership/events/no-live-event", "No Live Event"),
    ("membership/events/event_email.html", "legacy/membership/events/email", "Email: Event Registration"),
    ("membership/events/event_receipt_email.html", "legacy/membership/events/receipt-email", "Email: Event Receipt"),
    ("membership/events/error5.html", "legacy/membership/events/error", "Event Registration Error"),
    # ── Membership: layout + helper ───────────────────────────────────────────
    ("membership/layout.html", "legacy/membership/layout", "Membership Layout"),
    ("membership/render_helper.html", "legacy/membership/render-helper", "Membership Render Helper"),
    # ── Membership: registration flow ────────────────────────────────────────
    ("membership/registration/register_form.html", "legacy/membership/register", "Membership Registration Form"),
    ("membership/registration/verify_email.html", "legacy/membership/verify", "Email: Verify Email"),
    ("membership/registration/info_form.html", "legacy/membership/info-form", "Membership Info Form"),
    ("membership/registration/instructions_sent.html", "legacy/membership/instructions-sent", "Membership: Instructions Sent"),
    ("membership/registration/receipt.html", "legacy/membership/receipt", "Membership Receipt"),
    ("membership/registration/complete_registration.html", "legacy/membership/complete", "Membership: Registration Complete"),
    ("membership/registration/already_confirmed.html", "legacy/membership/already-confirmed", "Membership: Already Confirmed"),
    ("membership/registration/thanks_confirming.html", "legacy/membership/thanks", "Membership: Thank You"),
    ("membership/registration/resend.html", "legacy/membership/resend", "Membership: Resend Confirmation"),
    ("membership/registration/error1.html", "legacy/membership/error1", "Membership Error 1"),
    ("membership/registration/error2.html", "legacy/membership/error2", "Membership Error 2"),
    ("membership/registration/error3.html", "legacy/membership/error3", "Membership Error 3"),
    ("membership/registration/complete_email.html", "legacy/membership/complete-email", "Email: Registration Complete"),
    ("membership/registration/info_receipt_email.html", "legacy/membership/info-receipt", "Email: Info Receipt"),
    ("membership/registration/info_receipt_confirm_email.html", "legacy/membership/info-receipt-confirm", "Email: Info Receipt Confirmation"),
    ("membership/registration/deleting_email.html", "legacy/membership/deleting-email", "Email: Account Deletion"),
    # ── Membership: update flow ───────────────────────────────────────────────
    ("membership/update/enter_form.html", "legacy/membership/update/enter", "Membership Update: Enter Email"),
    ("membership/update/update_form.html", "legacy/membership/update/form", "Membership Update Form"),
    ("membership/update/thanks_update.html", "legacy/membership/update/thanks", "Membership Update: Thank You"),
    ("membership/update/error4.html", "legacy/membership/update/error", "Membership Update Error"),
    ("membership/update/update_email.html", "legacy/membership/update/email", "Email: Membership Update"),
    ("membership/update/update_receipt_email.html", "legacy/membership/update/receipt", "Email: Update Receipt"),
]


def _extract_content_block(raw: str) -> str:
    """
    Extract the content of {% block content %}...{% endblock %}.

    Handles nested blocks by tracking open/close depth. Falls back to the
    full file content if no 'content' block is found.
    """
    open_pat = re.compile(r"\{%-?\s*block\s+(\w+)\s*-?%\}", re.IGNORECASE)
    close_pat = re.compile(r"\{%-?\s*endblock(?:\s+\w+)?\s*-?%\}", re.IGNORECASE)

    # Find the first {% block content %} tag
    content_start_pos = None
    for m in open_pat.finditer(raw):
        if m.group(1).lower() == "content":
            content_start_pos = m.end()
            search_from = m.end()
            break

    if content_start_pos is None:
        return raw  # No content block — return entire file

    # Walk forward, tracking nesting depth
    pos = search_from
    depth = 1

    while depth > 0:
        next_open = open_pat.search(raw, pos)
        next_close = close_pat.search(raw, pos)

        if next_close is None:
            # No closing tag found — take the rest of the string
            return raw[content_start_pos:].strip()

        if next_open is not None and next_open.start() < next_close.start():
            depth += 1
            pos = next_open.end()
        else:
            depth -= 1
            if depth == 0:
                return raw[content_start_pos : next_close.start()].strip()
            pos = next_close.end()

    return raw[content_start_pos:].strip()


def _strip_jinja2(html: str) -> str:
    """Remove all remaining Jinja2 syntax from an HTML string."""
    # {# comments #}
    html = re.sub(r"\{#.*?#\}", "", html, flags=re.DOTALL)
    # {% ... %} block tags
    html = re.sub(r"\{%-?.*?-?%\}", "", html, flags=re.DOTALL)
    # {{ ... }} expressions
    html = re.sub(r"\{\{.*?\}\}", "", html, flags=re.DOTALL)
    return html.strip()


def extract_content(raw: str) -> str:
    """Extract block content and strip all Jinja2 syntax."""
    html = _extract_content_block(raw)
    return _strip_jinja2(html)


def extract_body_content(raw: str) -> str:
    """
    Extract content inside <body>...</body> for full-page templates that have
    no {% block content %} wrapper. Falls back to full content if no <body> tag.
    After extraction, Jinja2 syntax is stripped.
    """
    body_match = re.search(r"<body[^>]*>(.*)</body>", raw, re.DOTALL | re.IGNORECASE)
    inner = body_match.group(1) if body_match else raw
    return _strip_jinja2(inner)


class Command(BaseCommand):
    help = "Migrate old Flask HTML templates into the new CMS as published Page records."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        skipped_count = 0
        now = timezone.now()

        self.stdout.write(f"Reading templates from: {OLD_TEMPLATES_ROOT}\n")

        for rel_path, slug, title in PAGES_MAP:
            full_path = os.path.join(OLD_TEMPLATES_ROOT, rel_path)

            if not os.path.exists(full_path):
                self.stdout.write(self.style.WARNING(f"  MISSING  {rel_path}"))
                skipped_count += 1
                continue

            with open(full_path, encoding="utf-8") as f:
                raw = f.read()

            html = extract_content(raw)

            _, created = Page.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "html": html,
                    "css": "",
                    "status": "published",
                    "published_at": now,
                },
            )

            label = "Created" if created else "Updated"
            self.stdout.write(f"  {label:<8} {slug}")
            if created:
                created_count += 1
            else:
                updated_count += 1

        self._seed_homepage(now)

        total = created_count + updated_count
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone: {total} pages processed "
                f"({created_count} created, {updated_count} updated, {skipped_count} skipped)"
            )
        )

    def _seed_homepage(self, now):
        """Create or update the active HomePage using old home-post-event.html content."""
        src = os.path.join(OLD_TEMPLATES_ROOT, "home/home-post-event.html")
        if not os.path.exists(src):
            self.stdout.write(self.style.WARNING("\n  MISSING  home/home-post-event.html — skipping HomePage seed"))
            return

        with open(src, encoding="utf-8") as f:
            raw = f.read()

        html = extract_body_content(raw)

        # Deactivate any other active home pages first
        HomePage.objects.filter(is_active=True).update(is_active=False)

        home_page, created = HomePage.objects.update_or_create(
            name="Legacy Home",
            defaults={
                "html": html,
                "css": "",
                "status": "published",
                "is_active": True,
                "published_at": now,
            },
        )

        label = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"\n  {label}  HomePage 'Legacy Home' (active, published)"))
