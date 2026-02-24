"""
Pages app admin configuration.

Organized into modules by model:
- page: Page admin with GrapesJS editor
- home_page: HomePage admin
- menu: Menu admin
- footer_content: FooterContent admin
- media: MediaAsset admin
- forms: UniformForm and FormSubmission admin
- google_sheet: GoogleSheet admin
"""

from .assets.media import MediaAssetAdmin
from .content.home_page import HomePageAdmin
from .content.page import PageAdmin
from .forms.forms import FormSubmissionAdmin, UniformFormAdmin
from .integrations.google_sheet import GoogleSheetAdmin
from .layout.footer_content import FooterContentAdmin
from .layout.menu import MenuAdmin

__all__ = [
    # Pages
    "PageAdmin",
    "HomePageAdmin",
    # Layout
    "MenuAdmin",
    "FooterContentAdmin",
    # Media
    "MediaAssetAdmin",
    # Forms
    "UniformFormAdmin",
    "FormSubmissionAdmin",
    # Google Sheet
    "GoogleSheetAdmin",
]
