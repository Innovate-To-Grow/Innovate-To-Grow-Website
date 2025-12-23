from django.conf import settings
import ckeditor_uploader.fields
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import pages.models.page
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Form",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("form_uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("form_name", models.CharField(help_text="Internal form name (also visible in admin).", max_length=200, unique=True)),
                ("form_slug", models.SlugField(help_text="Optional machine-friendly slug for API / routing / admin filters.", max_length=200, unique=True)),
                ("form_description", models.TextField(blank=True, help_text="Description for editors / admins.", null=True)),
                ("login_required", models.BooleanField(default=False, help_text="Whether users must be authenticated to access this form.")),
                ("login_required_message", models.TextField(blank=True, help_text="Message displayed to anonymous users when login is required.", null=True)),
                ("default_verification_strategy", models.CharField(choices=[("none", "No verification"), ("email", "Email verification"), ("phone", "Phone verification"), ("both", "Email and phone verification")], default="none", help_text="High-level default verification strategy. Actual behavior is controlled by FormField flags and backend logic.", max_length=20)),
                ("submit_button_label", models.CharField(default="Submit", help_text="Text displayed on the submit button.", max_length=100)),
                ("success_message", models.TextField(blank=True, help_text="Message shown after successful submission.", null=True)),
                ("failure_message", models.TextField(blank=True, help_text="Optional message shown when submission fails.", null=True)),
                ("allow_multiple_submissions", models.BooleanField(default=True, help_text="Whether a user / contact can submit this form multiple times.")),
                ("max_submissions_per_user", models.PositiveIntegerField(blank=True, help_text="Optional cap on submissions per authenticated user (NULL means unlimited).", null=True)),
                ("submissions_count", models.PositiveIntegerField(default=0, help_text="Redundant: total number of submissions recorded.")),
                ("last_submission_at", models.DateTimeField(blank=True, help_text="Redundant: time of the most recent submission.", null=True)),
                ("published", models.BooleanField(default=False, help_text="Whether this form is active and can receive submissions.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Form",
                "verbose_name_plural": "Forms",
                "ordering": ["form_name"],
            },
        ),
        migrations.CreateModel(
            name="FormField",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("field_label", models.CharField(help_text="Human readable label displayed to users.", max_length=200)),
                ("field_key", models.SlugField(help_text="Machine key used as JSON key in submissions, e.g. 'email', 'full_name'. Must be unique within the same form.", max_length=200)),
                ("field_type", models.CharField(choices=[("text", "Text Input"), ("textarea", "Textarea"), ("link", "Link Input"), ("email", "Email"), ("phone", "Phone"), ("number", "Number"), ("select", "Dropdown Select"), ("checkbox", "Checkbox"), ("date", "Date"), ("code", "Verification Code Input")], help_text="Field input type / widget.", max_length=50)),
                ("field_required", models.BooleanField(default=False, help_text="Whether this field is required.")),
                ("field_placeholder", models.CharField(blank=True, help_text="Placeholder text shown in the input.", max_length=200, null=True)),
                ("field_help_text", models.CharField(blank=True, help_text="Additional helper text for the user.", max_length=255, null=True)),
                ("field_default", models.CharField(blank=True, help_text="Default value for this field, if any.", max_length=200, null=True)),
                ("field_group", models.CharField(blank=True, help_text="Optional group name for logical grouping in UI.", max_length=100, null=True)),
                ("field_distribution", models.CharField(blank=True, help_text="Optional layout hint, e.g. 'full', 'half-left', 'half-right'.", max_length=200, null=True)),
                ("field_order", models.IntegerField(default=0, help_text="Order of this field in the form.")),
                ("width_ratio", models.PositiveSmallIntegerField(default=12, help_text="Redundant: bootstrap-style column width (1-12).")),
                ("min_length", models.PositiveIntegerField(blank=True, help_text="Optional minimum length for text-based fields.", null=True)),
                ("max_length", models.PositiveIntegerField(blank=True, help_text="Optional maximum length for text-based fields.", null=True)),
                ("min_value", models.FloatField(blank=True, help_text="Optional minimum numeric value.", null=True)),
                ("max_value", models.FloatField(blank=True, help_text="Optional maximum numeric value.", null=True)),
                ("regex_pattern", models.CharField(blank=True, help_text="Optional regex pattern for additional validation.", max_length=255, null=True)),
                ("regex_error_message", models.CharField(blank=True, help_text="Error message when regex validation fails.", max_length=255, null=True)),
                ("is_unique", models.BooleanField(default=False, help_text="If True, submitted value must be unique across all submissions.")),
                ("options", models.JSONField(blank=True, help_text="Configuration JSON, e.g. a list of options for select fields, or other UI metadata.", null=True)),
                ("visibility_condition", models.JSONField(blank=True, help_text="Optional JSON condition for dynamic visibility, e.g. {'depends_on': 'is_student', 'equals': true}.", null=True)),
                ("extra_config", models.JSONField(blank=True, help_text="Extra UI or validation config. Redundant but flexible.", null=True)),
                ("is_contact_identity", models.BooleanField(default=False, help_text="If True, this field represents a contact identity (e.g. email/phone) that can be used for verification.")),
                ("requires_verification", models.BooleanField(default=False, help_text="If True, submission should only be considered verified when a matching ContactVerification succeeds.")),
                ("form", models.ForeignKey(help_text="Form that owns this field.", on_delete=django.db.models.deletion.CASCADE, related_name="fields", to="pages.form")),
            ],
            options={
                "verbose_name": "Form Field",
                "verbose_name_plural": "Form Fields",
                "ordering": ["form", "field_order"],
                "unique_together": {("form", "field_key")},
            },
        ),
        migrations.CreateModel(
            name="HomePage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Internal name to identify this home page version", max_length=200)),
                ("body", ckeditor_uploader.fields.RichTextUploadingField()),
                ("is_active", models.BooleanField(default=False, help_text="Only one home page can be active at a time")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Home Page",
                "verbose_name_plural": "Home Pages",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Menu",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.SlugField(help_text="Machine-readable name (e.g. 'main_nav', 'footer').", max_length=100, unique=True)),
                ("display_name", models.CharField(help_text="Human-readable name for admin display.", max_length=200)),
                ("description", models.TextField(blank=True, help_text="Optional description of this menu's purpose.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Menu",
                "verbose_name_plural": "Menus",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Page",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("title", models.CharField(help_text="Human readable title of the page.", max_length=200)),
                ("slug", models.CharField(help_text="User-defined slug. Supports nested paths, e.g. 'about/team'. Do NOT include leading or trailing '/'.", max_length=255, unique=True, validators=[pages.models.page.validate_nested_slug])),
                ("page_type", models.CharField(choices=[("page", "Rich Text Page"), ("external", "External URL"), ("form", "Form")], default="page", help_text="Page behavior type.", max_length=20)),
                ("page_body", ckeditor_uploader.fields.RichTextUploadingField(blank=True, help_text="Rich text content for 'page' type.", null=True)),
                ("external_url", models.URLField(blank=True, help_text="Target URL for 'external' type page.", null=True)),
                ("meta_title", models.CharField(blank=True, help_text="SEO title (will fall back to page title if empty).", max_length=255)),
                ("meta_description", models.TextField(blank=True, help_text="SEO description for search engines and social sharing.")),
                ("meta_keywords", models.CharField(blank=True, help_text="Comma-separated SEO keywords (optional, some search engines may ignore this).", max_length=255)),
                ("og_image", models.URLField(blank=True, help_text="Open Graph share image URL (e.g. for social media cards).", null=True)),
                ("canonical_url", models.URLField(blank=True, help_text="Canonical URL for SEO (optional, usually auto-resolved).", null=True)),
                ("meta_robots", models.CharField(blank=True, help_text="Robots meta tag value, e.g. 'index,follow' or 'noindex,nofollow'.", max_length=100)),
                ("slug_depth", models.PositiveIntegerField(default=0, help_text="Redundant: number of path segments (e.g. 'about/team' -> 1 slash).")),
                ("view_count", models.PositiveIntegerField(default=0, help_text="Redundant: total view count (may be updated externally).")),
                ("last_viewed_at", models.DateTimeField(blank=True, help_text="Redundant: timestamp of last page view.", null=True)),
                ("template_name", models.CharField(blank=True, help_text="Optional template name override for rendering this page.", max_length=255)),
                ("published", models.BooleanField(default=False, help_text="Whether this page is visible to the public.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("form", models.ForeignKey(blank=True, help_text="Linked form for 'form' type page.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pages", to="pages.form")),
            ],
            options={
                "verbose_name": "Page",
                "verbose_name_plural": "Pages",
                "ordering": ["slug"],
            },
        ),
        migrations.CreateModel(
            name="ContactVerification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("verification_uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("contact_type", models.CharField(choices=[("email", "Email"), ("phone", "Phone"), ("other", "Other")], help_text="Type of contact to verify (email / phone / other).", max_length=20)),
                ("contact_value", models.CharField(help_text="Actual contact value, e.g. email address or phone number.", max_length=255)),
                ("code", models.CharField(help_text="Verification code sent to the user.", max_length=20)),
                ("code_length", models.PositiveSmallIntegerField(default=6, help_text="Redundant: length of the code that was generated.")),
                ("purpose", models.CharField(choices=[("form_submission", "Form submission"), ("account", "Account related"), ("other", "Other")], default="form_submission", help_text="High-level purpose of this verification.", max_length=50)),
                ("is_used", models.BooleanField(default=False, help_text="Whether this code has already been successfully used.")),
                ("is_valid", models.BooleanField(default=True, help_text="Whether this code is still valid (not expired / not revoked).")),
                ("expires_at", models.DateTimeField(blank=True, help_text="Expiration time of this code.", null=True)),
                ("used_at", models.DateTimeField(blank=True, help_text="Timestamp when this code was successfully used.", null=True)),
                ("send_channel", models.CharField(blank=True, help_text="Channel used to send the code, e.g. 'email', 'sms', 'whatsapp'.", max_length=50)),
                ("send_count", models.PositiveIntegerField(default=1, help_text="Redundant: how many times this code (or this record) has been sent.")),
                ("last_sent_at", models.DateTimeField(default=django.utils.timezone.now, help_text="When the code was last sent.")),
                ("client_ip", models.GenericIPAddressField(blank=True, help_text="IP address of the client when the verification was requested.", null=True)),
                ("user_agent", models.TextField(blank=True, help_text="User agent string of the client.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("form", models.ForeignKey(blank=True, help_text="Form for which this verification is issued (optional).", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verifications", to="pages.form")),
                ("form_field", models.ForeignKey(blank=True, help_text="Specific field that triggered the verification (optional).", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verifications", to="pages.formfield")),
            ],
            options={
                "verbose_name": "Contact Verification",
                "verbose_name_plural": "Contact Verifications",
            },
        ),
        migrations.CreateModel(
            name="FormSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("submission_uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("completed", "Completed"), ("rejected", "Rejected"), ("spam", "Spam")], default="completed", help_text="High-level status of this submission.", max_length=20)),
                ("is_verified", models.BooleanField(default=False, help_text="Whether this submission passed required contact verification.")),
                ("data", models.JSONField(default=dict, help_text="Submitted field data as a JSON object.")),
                ("contact_email", models.EmailField(blank=True, help_text="Redundant: main email extracted from data for indexing / filtering.", max_length=254, null=True)),
                ("contact_phone", models.CharField(blank=True, help_text="Redundant: main phone number extracted from data.", max_length=50, null=True)),
                ("client_ip", models.GenericIPAddressField(blank=True, help_text="IP address from where the form was submitted.", null=True)),
                ("user_agent", models.TextField(blank=True, help_text="User agent string of the client who submitted the form.", null=True)),
                ("referrer", models.TextField(blank=True, help_text="HTTP referrer when the form was submitted.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("submitted_at", models.DateTimeField(auto_now_add=True, help_text="Redundant: alias of created_at, useful for reporting.")),
                ("processing_time_ms", models.PositiveIntegerField(blank=True, help_text="Optional: server-side processing time in milliseconds.", null=True)),
                ("extra_metadata", models.JSONField(blank=True, default=dict, help_text="Additional metadata for this submission (for analytics or integrations).")),
                ("form", models.ForeignKey(help_text="Form to which this submission belongs.", on_delete=django.db.models.deletion.CASCADE, related_name="submissions", to="pages.form")),
                ("user", models.ForeignKey(blank=True, help_text="Authenticated user who submitted the form (if any).", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="form_submissions", to=settings.AUTH_USER_MODEL)),
                ("verification", models.ForeignKey(blank=True, help_text="Associated contact verification record, if any.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="submissions", to="pages.contactverification")),
            ],
            options={
                "verbose_name": "Form Submission",
                "verbose_name_plural": "Form Submissions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MenuPageLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.IntegerField(default=0, help_text="Display order (lower numbers appear first).")),
                ("custom_title", models.CharField(blank=True, help_text="Override the page title for this menu (optional).", max_length=200, null=True)),
                ("css_classes", models.CharField(blank=True, help_text="Additional CSS classes for styling.", max_length=255, null=True)),
                ("icon", models.CharField(blank=True, help_text="Icon class name (e.g. 'fa-home' for FontAwesome).", max_length=100, null=True)),
                ("open_in_new_tab", models.BooleanField(default=False, help_text="Whether to open the link in a new browser tab.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("menu", models.ForeignKey(help_text="The menu this link belongs to.", on_delete=django.db.models.deletion.CASCADE, to="pages.menu")),
                ("page", models.ForeignKey(help_text="The page being linked.", on_delete=django.db.models.deletion.CASCADE, to="pages.page")),
            ],
            options={
                "verbose_name": "Menu Page Link",
                "verbose_name_plural": "Menu Page Links",
                "ordering": ["menu", "order"],
            },
        ),
        migrations.AddField(
            model_name="menu",
            name="pages",
            field=models.ManyToManyField(blank=True, help_text="Pages included in this menu.", related_name="menus", through="pages.MenuPageLink", to="pages.page"),
        ),
        migrations.AddIndex(
            model_name="contactverification",
            index=models.Index(fields=["contact_type", "contact_value"], name="pages_conta_contact_05b93e_idx"),
        ),
        migrations.AddIndex(
            model_name="contactverification",
            index=models.Index(fields=["is_used", "is_valid"], name="pages_conta_is_used_b25c25_idx"),
        ),
        migrations.AddIndex(
            model_name="formsubmission",
            index=models.Index(fields=["form", "status"], name="pages_forms_form_id__8a4777_idx"),
        ),
        migrations.AddIndex(
            model_name="formsubmission",
            index=models.Index(fields=["is_verified"], name="pages_forms_is_veri_5132bb_idx"),
        ),
        migrations.AddIndex(
            model_name="formsubmission",
            index=models.Index(fields=["contact_email"], name="pages_forms_contact_c979b3_idx"),
        ),
        migrations.AddIndex(
            model_name="formsubmission",
            index=models.Index(fields=["contact_phone"], name="pages_forms_contact_3e7ca0_idx"),
        ),
        migrations.AddIndex(
            model_name="menupagelink",
            index=models.Index(fields=["menu", "order"], name="pages_menup_menu_id_7ee474_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="formfield",
            unique_together={("form", "field_key")},
        ),
        migrations.AlterUniqueTogether(
            name="menupagelink",
            unique_together={("menu", "page")},
        ),
    ]
