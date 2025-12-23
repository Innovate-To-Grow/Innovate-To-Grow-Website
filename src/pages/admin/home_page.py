from django import forms
from django.contrib import admin
from ..models import HomePage


class HomePageAdminForm(forms.ModelForm):
    """Custom form with hidden textarea for Quill integration."""
    
    body = forms.CharField(
        widget=forms.Textarea(attrs={
            'id': 'id_body',
            'style': 'display: none;',  # Hidden, Quill will show its own editor
        }),
        required=False,
    )

    class Meta:
        model = HomePage
        fields = '__all__'


@admin.register(HomePage)
class HomePageAdmin(admin.ModelAdmin):
    form = HomePageAdminForm
    list_display = ('name', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')

    # Custom template for Quill editor with real-time preview
    change_form_template = 'admin/pages/homepage/change_form.html'
    
    class Media:
        css = {
            'all': (
                'pages/css/admin_preview.css',
                'pages/css/quill-admin.css',
            )
        }
        # Quill JS is loaded via CDN in the template
