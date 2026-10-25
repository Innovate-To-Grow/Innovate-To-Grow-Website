"""Unfold branding, color palette, and static asset configuration."""

from django.templatetags.static import static

UNFOLD_THEME = {
    "SITE_TITLE": "I2G Admin",
    "SITE_HEADER": "Innovate To Grow",
    "SITE_ICON": lambda request: static("images/i2glogo.png"),
    "SITE_LOGO": lambda request: static("images/i2glogo.png"),
    "COLORS": {
        "primary": {
            "50": "#f9f9ff",
            "100": "#ebf1ff",
            "200": "#d5e3ff",
            "300": "#a7c8ff",
            "400": "#82adf0",
            "500": "#6792d4",
            "600": "#305f9d",
            "700": "#0f4784",
            "800": "#003061",
            "900": "#001b3c",
            "950": "#001026",
        },
    },
    "STYLES": [
        lambda request: static("admin/css/google-material-admin.css"),
        lambda request: static("admin/css/tabs.css"),
        lambda request: static("admin/css/file-input.css"),
    ],
    "SCRIPTS": [
        lambda request: static("admin/js/htmx-csp-config.js"),
    ],
}
