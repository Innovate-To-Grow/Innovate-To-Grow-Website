"""
Menu model for organizing navigation items.

A Menu contains a JSON structure of navigation items that can be:
- App: Link to an internal app route (e.g. /, /event, /news)
- External: External URL
- Items can have children (submenus)
"""

from django.db import models

from core.models import ProjectControlModel


def default_menu_items():
    """
    Default menu items structure.

    Each item has:
    - type: 'external' | 'app'
    - title: Display title
    - url: URL for the link
    - icon: Optional icon class
    - open_in_new_tab: Boolean
    - children: Nested items (for submenus)
    """
    return [{"type": "app", "title": "Home", "url": "/", "icon": "fa-home", "open_in_new_tab": False, "children": []}]


class Menu(ProjectControlModel):
    """
    Menu container model.

    Stores navigation items as JSON for flexible editing.
    Examples: main navigation, footer links, sidebar menu.
    """

    # ------------------------------ Identification ------------------------------

    name = models.SlugField(max_length=100, unique=True, help_text="Machine-readable name (e.g. 'main_nav', 'footer').")
    display_name = models.CharField(max_length=200, blank=True, help_text="Auto-generated from name if not provided.")
    description = models.TextField(blank=True, null=True, help_text="Optional description of this menu's purpose.")

    # ------------------------------ Menu Items (JSON) ------------------------------

    items = models.JSONField(
        default=default_menu_items,
        help_text="JSON array of menu items. Each item can be an external link or app route.",
    )

    # ------------------------------ Methods ------------------------------

    def __str__(self) -> str:
        return self.display_name

    class Meta:
        db_table = "pages_menu"
        ordering = ["name"]
        verbose_name = "Menu"
        verbose_name_plural = "Menus"
