from rest_framework import serializers
from ..models import Menu, FooterContent


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
        from pages.models import HomePage, Page
        
        processed = []
        for item in items:
            processed_item = {
                'type': item.get('type', 'page'),
                'title': item.get('title', ''),
                'icon': item.get('icon', ''),
                'open_in_new_tab': item.get('open_in_new_tab', False),
            }
            
            if item.get('type') == 'home':
                # Inject active home page info
                home_page = HomePage.get_active()
                processed_item['url'] = '/'
                processed_item['page_type'] = 'home'
                if home_page:
                    processed_item['home_active'] = True
                    processed_item['home_name'] = home_page.name
                else:
                    processed_item['home_active'] = False
                    
            elif item.get('type') == 'page':
                page_slug = item.get('page_slug', '')
                processed_item['page_slug'] = page_slug
                processed_item['url'] = f'/pages/{page_slug}' if page_slug else '#'
                processed_item['page_type'] = 'page'
                
                # Try to get page title if not set
                if not processed_item['title'] and page_slug:
                    try:
                        page = Page.objects.get(slug=page_slug)
                        processed_item['title'] = page.title
                    except Page.DoesNotExist:
                        pass
                        
            elif item.get('type') == 'external':
                processed_item['url'] = item.get('url', '#')
                processed_item['page_type'] = 'external'
            
            # Process children recursively
            children = item.get('children', [])
            if children:
                processed_item['children'] = self._process_items(children)
            else:
                processed_item['children'] = []
            
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
