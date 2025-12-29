from django.contrib import admin
from .page_component import PageComponentForm
from ..models import HomePage, PageComponent


class HomePageComponentInline(admin.StackedInline):
    model = PageComponent
    fk_name = "home_page"
    extra = 0
    form = PageComponentForm
    fields = ("component_type", "order", "html_content", "config", "css_file", "css_code", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at", "css_file")
    ordering = ("order", "id")
    show_change_link = True


@admin.register(HomePage)
class HomePageAdmin(admin.ModelAdmin):
    inlines = [HomePageComponentInline]
    list_display = ('name', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
