"""
Prospect admin configuration.
"""

from django.contrib import admin
from django.utils.html import format_html
from ..models import Prospect
from ..services.google_sheets_sync import get_sync_service


@admin.register(Prospect)
class ProspectAdmin(admin.ModelAdmin):
    """
    Admin for Prospect model.
    """
    
    list_display = (
        'email',
        'get_full_name',
        'when_input',
        'when_signed_up_as_member',
        'primary_collision',
        'secondary_collision',
        'phone_collision',
        'get_bounced_status',
    )
    
    list_filter = (
        'primary_collision',
        'secondary_collision',
        'phone_collision',
        'when_input',
        'when_signed_up_as_member',
    )
    
    search_fields = (
        'email',
        'secondary_email',
        'first_name',
        'last_name',
        'phone_number',
    )
    
    readonly_fields = (
        'when_input',
        'when_last_checked',
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('first_name', 'last_name', 'email', 'secondary_email', 'phone_number')
        }),
        ('Timestamps', {
            'fields': ('when_input', 'when_signed_up_as_member', 'when_last_checked')
        }),
        ('Bounce Information', {
            'fields': (
                'primary_bounced_at',
                'secondary_bounced_at',
                'phone_bounced_at',
            )
        }),
        ('Collision Detection', {
            'fields': (
                'primary_collision',
                'secondary_collision',
                'phone_collision',
            )
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    actions = ['sync_to_google_sheets', 'sync_from_google_sheets', 'update_collisions']
    
    def get_full_name(self, obj):
        """Get full name or email if no name."""
        name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return name or obj.email
    get_full_name.short_description = 'Name'
    
    def get_bounced_status(self, obj):
        """Display bounce status."""
        bounced = []
        if obj.primary_bounced_at:
            bounced.append('Primary')
        if obj.secondary_bounced_at:
            bounced.append('Secondary')
        if obj.phone_bounced_at:
            bounced.append('Phone')
        return ', '.join(bounced) if bounced else '-'
    get_bounced_status.short_description = 'Bounced'
    
    @admin.action(description='Sync prospects to Google Sheets')
    def sync_to_google_sheets(self, request, queryset):
        """Sync prospects to Google Sheets."""
        try:
            sync_service = get_sync_service()
            sync_service.ensure_sheet_structure()
            result = sync_service.sync_prospects_to_sheet()
            if result['success']:
                self.message_user(request, f"Successfully synced {result['rows_synced']} prospects to Google Sheets.")
            else:
                self.message_user(request, f"Error syncing to Google Sheets: {', '.join(result['errors'])}", level='ERROR')
        except Exception as e:
            self.message_user(request, f"Error syncing to Google Sheets: {str(e)}", level='ERROR')
    
    @admin.action(description='Sync prospects from Google Sheets')
    def sync_from_google_sheets(self, request, queryset):
        """Sync prospects from Google Sheets to database."""
        try:
            sync_service = get_sync_service()
            result = sync_service.sync_prospects_from_sheet()
            if result['success']:
                self.message_user(request, f"Successfully synced {result['rows_synced']} prospects from Google Sheets.")
            else:
                self.message_user(request, f"Error syncing from Google Sheets: {', '.join(result['errors'])}", level='ERROR')
        except Exception as e:
            self.message_user(request, f"Error syncing from Google Sheets: {str(e)}", level='ERROR')
    
    @admin.action(description='Update collision detection for selected prospects')
    def update_collisions(self, request, queryset):
        """Update collision detection for selected prospects."""
        from ..services.collision_detection import update_prospect_collisions
        updated = 0
        for prospect in queryset:
            update_prospect_collisions(prospect)
            updated += 1
        self.message_user(request, f'Updated collision detection for {updated} prospect(s).')
