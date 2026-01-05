from rest_framework import serializers

from layout.models import MenuPageLink
from layout.serializers import MenuSerializer as LayoutMenuSerializer
from sheets.models import Sheet

from ..models import FormSubmission, HomePage, Page, PageComponent, UniformForm


class SheetSerializer(serializers.ModelSerializer):
    """Serializer for retrieving sheet data."""

    class Meta:
        model = Sheet
        fields = [
            "id",
            "name",
            "description",
            "columns",
            "data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PageComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageComponent
        fields = [
            "id",
            "component_type",
            "order",
            "html_content",
            "css_file",
            "css_code",
            "js_code",
            "config",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PageSerializer(serializers.ModelSerializer):
    components = PageComponentSerializer(many=True, read_only=True)

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
            "published",
            "components",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class HomePageSerializer(serializers.ModelSerializer):
    components = PageComponentSerializer(many=True, read_only=True)

    class Meta:
        model = HomePage
        fields = ["id", "name", "is_active", "components", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


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


# Re-export MenuSerializer to keep existing import paths working
MenuSerializer = LayoutMenuSerializer


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
