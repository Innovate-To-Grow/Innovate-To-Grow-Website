"""Configuration constants for the page-freeze service."""

# Outbound fetch limits.
FETCH_TIMEOUT = 20  # seconds, per request
MAX_REDIRECTS = 5
MAX_DOCUMENT_BYTES = 5_000_000  # raw HTML of the source page
MAX_ASSET_BYTES = 2_000_000  # per sub-resource (image, font, stylesheet)
# Final self-contained document. Base64-inlining bloats bytes ~33%, so this sits
# above MAX_DOCUMENT_BYTES to leave room for inlined assets.
MAX_TOTAL_FROZEN_BYTES = 8_000_000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Preset removal groups. Each preset key maps to the CSS selectors decomposed
# from the page before inlining. These are intentionally heuristic — the admin's
# free-form "extra selectors" field is the escape hatch for anything they miss.
REMOVAL_PRESETS = {
    "header": ["header", "[role=banner]", ".site-header", "#site-header", "#header", ".page-header"],
    "nav": ["nav", "[role=navigation]", ".navbar", ".main-nav", ".site-nav", "#nav", "#navigation"],
    "footer": ["footer", "[role=contentinfo]", ".site-footer", "#site-footer", "#footer", ".page-footer"],
    "cookie_consent": [
        "#cookie-banner",
        ".cookie-banner",
        ".cookie-consent",
        "#cookie-consent",
        "[class*=cookie-consent]",
        "[id*=cookie-consent]",
        ".cookie-notice",
        ".gdpr",
        "#gdpr",
        ".consent-banner",
    ],
    "ads": [
        ".ad",
        ".ads",
        ".advert",
        ".advertisement",
        "ins.adsbygoogle",
        "[id^=google_ads]",
        "[class*=advert]",
        "[id^=ad-]",
        "[class^=ad-]",
    ],
}

REMOVAL_PRESET_KEYS = tuple(REMOVAL_PRESETS.keys())
