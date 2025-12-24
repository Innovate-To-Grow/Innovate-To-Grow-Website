"""
I2G Member Group admin configuration.
"""
from django.contrib import admin

from ..models import I2GMemberGroup


@admin.register(I2GMemberGroup)
class I2GMemberGroupAdmin(admin.ModelAdmin):
    """Admin for I2GMemberGroup (proxy for Django Group)."""
    
    list_display = ('name', 'is_default_group_display', 'get_members_count_display')
    search_fields = ('name',)
    filter_horizontal = ('permissions',)
    
    @admin.display(description='Default Group', boolean=True)
    def is_default_group_display(self, obj):
        return obj.is_default_group()
    
    @admin.display(description='Members Count')
    def get_members_count_display(self, obj):
        return obj.get_members_count()
    
    # Custom action to create default groups
    actions = ['create_default_groups']
    
    @admin.action(description='Create default I2G groups')
    def create_default_groups(self, request, queryset):
        I2GMemberGroup.create_default_groups()
        self.message_user(request, 'Default I2G groups have been created.')

