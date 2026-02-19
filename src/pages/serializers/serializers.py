from rest_framework import serializers

from ..models import (
    FooterContent,
    FormSubmission,
    HomePage,
    Menu,
    MenuPageLink,
    Page,
    PageComponent,
    UniformForm,
)


class PageComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageComponent
        fields = [
            "id",
            "name",
            "component_type",
            "order",
            "is_enabled",
            "html_content",
            "css_file",
            "css_code",
            "js_code",
            "config",
            "google_sheet",
            "google_sheet_style",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PageSerializer(serializers.ModelSerializer):
    components = PageComponentSerializer(many=True, read_only=True)
    published = serializers.BooleanField(read_only=True)  # computed from status

    class Meta:
        model = Page
        fields = [
            "id",
            "title",
            "slug",
            "meta_title",
            "meta_description",
            "meta_keywords",
            "og_image",
            "canonical_url",
            "meta_robots",
            "template_name",
            "status",
            "published",
            "components",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at", "published"]


class HomePageSerializer(serializers.ModelSerializer):
    components = PageComponentSerializer(many=True, read_only=True)
    published = serializers.BooleanField(read_only=True)  # computed from status

    class Meta:
        model = HomePage
        fields = [
            "id",
            "name",
            "is_active",
            "status",
            "published",
            "components",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "published"]


class UniformFormSerializer(serializers.ModelSerializer):
    """Serializer for retrieving form definitions."""

    class Meta:
        model = UniformForm
        fields = [
            "id",
            "form_uuid",
            "name",
            "slug",
            "description",
            "fields",
            "submit_button_text",
            "success_message",
            "redirect_url",
            "allow_anonymous",
            "login_required",
            "is_active",
            "published",
        ]
        read_only_fields = ["id", "form_uuid", "submission_count"]


class FormSubmissionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating form submissions."""

    class Meta:
        model = FormSubmission
        fields = ["form", "data"]

    def validate(self, attrs):
        """Validate submission data against form field definitions."""
        form = attrs["form"]
        data = attrs["data"]

        # Use the form's built-in validation method
        errors = form.validate_submission_data(data)
        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data):
        """Create submission with metadata from request."""
        request = self.context.get("request")

        # Extract client IP
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR")

        # Create the submission
        submission = FormSubmission.objects.create(
            form=validated_data["form"],
            user=request.user if request.user.is_authenticated else None,
            data=validated_data["data"],
            ip_address=ip_address,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            referrer=request.META.get("HTTP_REFERER", ""),
        )

        # Increment form submission count
        submission.form.increment_submission_count()

        # TODO: Send email notification if enabled
        # This will be implemented in a separate utility function

        return submission


class FormSubmissionListSerializer(serializers.ModelSerializer):
    """Serializer for listing submissions (admin only)."""

    form_name = serializers.CharField(source="form.name", read_only=True)
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = FormSubmission
        fields = [
            "id",
            "submission_uuid",
            "form_name",
            "user_display",
            "status",
            "submitted_at",
        ]

    def get_user_display(self, obj):
        """Return username or 'Anonymous'."""
        return obj.user.username if obj.user else "Anonymous"


class MenuSerializer(serializers.ModelSerializer):
    """
    Serializer for Menu with JSON items.

    Processes items to:
    - Inject active HomePage info for 'home' type items
    - Resolve page slugs to full URLs for 'page' type items
    """

    items = serializers.SerializerMethodField()

    class Meta:
        model = Menu
        fields = ["id", "name", "display_name", "description", "items", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_items(self, obj):
        """Process menu items with dynamic data injection."""
        raw_items = obj.items or []
        return self._process_items(raw_items)

    def _process_items(self, items):
        """Recursively process menu items."""
        processed = []
        for item in items:
            processed_item = {
                "type": item.get("type", "page"),
                "title": item.get("title", ""),
                "icon": item.get("icon", ""),
                "open_in_new_tab": item.get("open_in_new_tab", False),
            }

            if item.get("type") == "home":
                # Inject active home page info
                home_page = HomePage.get_active()
                processed_item["url"] = "/"
                processed_item["page_type"] = "home"
                if home_page:
                    processed_item["home_active"] = True
                    processed_item["home_name"] = home_page.name
                else:
                    processed_item["home_active"] = False

            elif item.get("type") == "page":
                page_slug = item.get("page_slug", "")
                processed_item["page_slug"] = page_slug
                processed_item["url"] = f"/pages/{page_slug}" if page_slug else "#"
                processed_item["page_type"] = "page"

                # Try to get page title if not set
                if not processed_item["title"] and page_slug:
                    try:
                        page = Page.objects.get(slug=page_slug)
                        processed_item["title"] = page.title
                    except Page.DoesNotExist:
                        pass

            elif item.get("type") == "external":
                processed_item["url"] = item.get("url", "#")
                processed_item["page_type"] = "external"

            # Process children recursively
            children = item.get("children", [])
            if children:
                processed_item["children"] = self._process_items(children)
            else:
                processed_item["children"] = []

            processed.append(processed_item)

        return processed


class FooterContentSerializer(serializers.ModelSerializer):
    """Serializer for FooterContent structured JSON."""

    class Meta:
        model = FooterContent
        fields = [
            "id",
            "name",
            "slug",
            "content",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class MenuPageLinkSerializer(serializers.ModelSerializer):
    """Serializer for the legacy Menu-Page link objects."""

    class Meta:
        model = MenuPageLink
        fields = [
            "id",
            "menu",
            "page",
            "order",
            "custom_title",
            "css_classes",
            "icon",
            "open_in_new_tab",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
