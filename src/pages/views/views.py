from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import FormSubmission, HomePage, Page, UniformForm
from ..serializers import (
    FormSubmissionCreateSerializer,
    FormSubmissionListSerializer,
    HomePageSerializer,
    PageSerializer,
    UniformFormSerializer,
)


class PreviewPopupView(TemplateView):
    """
    Render the popup preview page for live editing.
    """

    template_name = "pages/preview_popup.html"


class ComponentPreviewView(TemplateView):
    """
    Render the component preview page for live editing PageComponents.
    """

    template_name = "pages/component_preview.html"


class HomePageAPIView(APIView):
    """
    Retrieve the currently active home page.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        home_page = HomePage.get_active()
        if not home_page:
            return Response(
                {"detail": "No active home page found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = HomePageSerializer(home_page)
        return Response(serializer.data)


class PageListAPIView(ListAPIView):
    """
    List all pages (for menu editor dropdown).
    """

    serializer_class = PageSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Page.objects.all().order_by("title")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        # Return simplified list for menu editor
        pages = [{"slug": p.slug, "title": p.title} for p in queryset]
        return Response({"pages": pages})


class PageRetrieveAPIView(RetrieveAPIView):
    """
    Retrieve a page by slug.
    """

    queryset = Page.objects.all()
    serializer_class = PageSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    permission_classes = [AllowAny]


class UniformFormRetrieveAPIView(RetrieveAPIView):
    """
    Retrieve a form by slug for rendering.

    Returns form configuration including fields, settings, and display options.
    Only returns active and published forms.
    """

    queryset = UniformForm.objects.filter(is_active=True, published=True)
    serializer_class = UniformFormSerializer
    lookup_field = "slug"
    permission_classes = [AllowAny]


class FormSubmissionCreateAPIView(CreateAPIView):
    """
    Create a form submission.

    Validates submission data against form field definitions and stores
    the submission with metadata (IP address, user agent, etc.).
    """

    serializer_class = FormSubmissionCreateSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        """Additional validation and submission limit checking."""
        form = serializer.validated_data["form"]

        # Check if form is active and published
        if not form.is_active or not form.published:
            raise ValidationError("This form is not accepting submissions.")

        # Check login requirement
        if form.login_required and not self.request.user.is_authenticated:
            raise PermissionDenied("You must be logged in to submit this form.")

        # Check submission limits for authenticated users
        if self.request.user.is_authenticated and form.max_submissions_per_user > 0:
            user_submission_count = FormSubmission.objects.filter(form=form, user=self.request.user).count()

            if user_submission_count >= form.max_submissions_per_user:
                raise ValidationError(
                    f"You have reached the maximum number of submissions ({form.max_submissions_per_user}) for this form."
                )

        # Create the submission
        serializer.save()


class FormSubmissionListAPIView(ListAPIView):
    """
    List submissions for a specific form (admin only).

    Returns all submissions for the specified form, ordered by submission date.
    """

    serializer_class = FormSubmissionListSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        form_slug = self.kwargs["form_slug"]
        return FormSubmission.objects.filter(form__slug=form_slug)
