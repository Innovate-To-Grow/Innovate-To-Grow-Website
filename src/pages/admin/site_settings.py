from django.contrib import admin
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from ..models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Admin interface for SiteSettings singleton model."""

    fieldsets = (
        ('Home Page Configuration', {
            'fields': ('home_page_mode',),
            'description': 'Select which home page variant should be displayed on the site.',
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at')
    list_display = ('__str__', 'home_page_mode', 'updated_at')
    list_display_links = ('__str__',)

    def has_add_permission(self, request):
        """Prevent adding new instances if one already exists."""
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting the singleton instance."""
        return False

    def changelist_view(self, request, extra_context=None):
        """Redirect to the edit page if instance exists, or create if it doesn't."""
        if SiteSettings.objects.exists():
            instance = SiteSettings.get_instance()
            return HttpResponseRedirect(
                reverse('admin:pages_sitesettings_change', args=[instance.pk])
            )
        return super().changelist_view(request, extra_context)

    def get_readonly_fields(self, request, obj=None):
        """Make fields readonly if instance already exists."""
        readonly = list(self.readonly_fields)
        if obj:
            # If editing existing instance, all fields are editable except timestamps
            pass
        return readonly



