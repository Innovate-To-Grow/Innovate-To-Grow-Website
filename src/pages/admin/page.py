from django.contrib import admin
from ..models import Page

@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'page_type', 'published', 'view_count', 'updated_at')
    list_filter = ('published', 'page_type', 'created_at')
    search_fields = ('title', 'slug', 'page_body')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('page_uuid', 'slug_depth', 'view_count', 'last_viewed_at', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'page_type', 'page_uuid')
        }),
        ('Content', {
            'fields': ('page_body', 'external_url', 'template_name'),
            'classes': ('extrapretty',)
        }),
        ('SEO & Metadata', {
            'fields': ('meta_title', 'meta_description', 'meta_keywords', 
                      'og_image', 'canonical_url', 'meta_robots'),
            'classes': ('collapse',)
        }),
        ('Publishing', {
            'fields': ('published', 'created_at', 'updated_at'),
        }),
        ('Statistics', {
            'fields': ('view_count', 'last_viewed_at', 'slug_depth'),
            'classes': ('collapse',)
        }),
    )
