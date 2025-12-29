"""
Menu model for organizing navigation items.

A Menu contains a JSON structure of navigation items that can be:
- Home: Link to the home page
- Page: Link to an internal Page
- External: External URL
- Items can have children (submenus)
"""

from django.db import models


def default_menu_items():
    """
    Default menu items structure.
    
    Each item has:
    - type: 'home' | 'page' | 'external'
    - title: Display title
    - url: For external links
    - page_slug: For page links
    - icon: Optional icon class
    - open_in_new_tab: Boolean
    - children: Nested items (for submenus)
    """
    return [
        {
            "type": "home",
            "title": "Home",
            "icon": "",
            "open_in_new_tab": False,
            "children": []
        }
    ]


class Menu(models.Model):
    """
    Menu container model.

    Stores navigation items as JSON for flexible editing.
    Examples: main navigation, footer links, sidebar menu.
    """

    # ------------------------------ Identification ------------------------------

    name = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Machine-readable name (e.g. 'main_nav', 'footer')."
    )
    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Auto-generated from name if not provided."
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of this menu's purpose."
    )

    # ------------------------------ Menu Items (JSON) ------------------------------

    items = models.JSONField(
        default=default_menu_items,
        help_text="JSON array of menu items. Each item can be home, page, or external link."
    )

    # ------------------------------ Legacy Fields (kept for backward compatibility) ------

    pages = models.ManyToManyField(
        'pages.Page',
        through='MenuPageLink',
        related_name='menus',
        blank=True,
        help_text="Legacy: Pages included in this menu."
    )

    # ------------------------------ Timestamps ------------------------------

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------ Methods ------------------------------

    def get_pages(self):
        """
        Return all pages in order (legacy method).
        """
        return self.pages.order_by('menupagelink__order')

    def get_page_links(self):
        """
        Return all MenuPageLink objects for this menu in order (legacy method).
        """
        return self.menupagelink_set.select_related('page').order_by('order')

    def __str__(self) -> str:
        return self.display_name

    class Meta:
        db_table = "pages_menu"
        ordering = ['name']
        verbose_name = "Menu"
        verbose_name_plural = "Menus"


class MenuPageLink(models.Model):
    """
    Through model for Menu-Page relationship.

    Stores the order and additional display options for each page in a menu.
    """

    menu = models.ForeignKey(
        Menu,
        on_delete=models.CASCADE,
        help_text="The menu this link belongs to."
    )
    page = models.ForeignKey(
        'pages.Page',
        on_delete=models.CASCADE,
        help_text="The page being linked."
    )
    order = models.IntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)."
    )

    # ------------------------------ Display Options ------------------------------

    custom_title = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Override the page title for this menu (optional)."
    )
    css_classes = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Additional CSS classes for styling."
    )
    icon = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Icon class name (e.g. 'fa-home' for FontAwesome)."
    )
    open_in_new_tab = models.BooleanField(
        default=False,
        help_text="Whether to open the link in a new browser tab."
    )

    # ------------------------------ Timestamps ------------------------------

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------ Methods ------------------------------

    @property
    def display_title(self) -> str:
        """Return custom_title if set, otherwise page title."""
        return self.custom_title or self.page.title

    def get_url(self) -> str:
        """Return the URL for this menu link."""
        return self.page.get_absolute_url()

    def __str__(self) -> str:
        return f"[{self.menu.name}] {self.display_title}"

    class Meta:
        db_table = "pages_menupagelink"
        ordering = ['menu', 'order']
        verbose_name = "Menu Page Link"
        verbose_name_plural = "Menu Page Links"
        unique_together = [['menu', 'page']]
        indexes = [
            models.Index(fields=['menu', 'order'], name='pages_menu_menu_id_c18fe0_idx'),
        ]
