"""
Build a ZIP archive for importing captured legacy pages into the Django site.

Creates a manifest.json with page entries, each containing a single HTML component
with cleaned content extracted from the old Flask site's rendered pages.

Cleaning steps:
- Extracts only the main content area (<div id="main">) from each page
- Removes the navigation bar, footer, <head>, <html>/<body> wrapper
- Removes page-specific CSS/JS that are already loaded globally
- Replaces localhost:5050 references with relative paths
"""
import json
import os
import re
import zipfile
from datetime import datetime, timezone

from bs4 import BeautifulSoup

CAPTURED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captured_pages")
OUTPUT_ZIP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legacy_pages_import.zip")

# Map of filename (without .html) -> (slug, title)
PAGE_METADATA = {
    "home-post-event": ("legacy/home", "Legacy Home"),
    "about": ("legacy/about", None),
    "terms_and_conditions": ("legacy/privacy", None),
    "engineering-capstone": ("legacy/engineering-capstone", None),
    "about_EngSL": ("legacy/about-engsl", None),
    "software-capstone": ("legacy/software-capstone", None),
    "event": ("legacy/event", None),
    "schedule": ("legacy/schedule", None),
    "projects-teams": ("legacy/projects-teams", None),
    "judges": ("legacy/judges", None),
    "attendees": ("legacy/attendees", None),
    "students": ("legacy/students", None),
    "acknowledgement": ("legacy/acknowledgement", None),
    "past-events": ("legacy/past-events", None),
    "projects": ("legacy/projects", None),
    "current-projects": ("legacy/current-projects", None),
    "project-submission": ("legacy/project-submission", None),
    "sample-proposals": ("legacy/sample-proposals", None),
    "partnership": ("legacy/partnership", None),
    "sponsorship": ("legacy/sponsorship", None),
    "faq": ("legacy/faqs", None),
    "I2G-student-agreement": ("legacy/student-agreement", None),
    "ferpa": ("legacy/ferpa", None),
    "i2g-students-preparation": ("legacy/students-preparation", None),
    "video-preparation": ("legacy/video-preparation", None),
    "capstone-purchasing-reimbursement": ("legacy/capstone-purchasing", None),
    "contact-us": ("legacy/contact-us", None),
    "judging": ("legacy/judging", None),
    "template": ("legacy/template", None),
    "template-email-team-students": ("legacy/template-email-team-students", None),
    "I2G-project-sponsor-acknowledgement": ("legacy/sponsor-acknowledgement", None),
    "home-during-event": ("legacy/home-during-event", None),
    "2025-fall-event": ("legacy/2025-fall-event", None),
    "2025-spring-event": ("legacy/2025-spring-event", None),
    "2024-fall-event": ("legacy/2024-fall-event", None),
    "2024-spring-event": ("legacy/2024-spring-event", None),
    "2023-fall-event": ("legacy/2023-fall-event", None),
    "2023-spring-event": ("legacy/2023-spring-event", None),
    "2022-fall-event": ("legacy/2022-fall-event", None),
    "2022-spring-event": ("legacy/2022-spring-event", None),
    "2021-fall-event": ("legacy/2021-fall-event", None),
    "2021-spring-event": ("legacy/2021-spring-event", None),
    "2020-fall-post-event": ("legacy/2020-fall-event", None),
    "2014-sponsors": ("legacy/2014-sponsors", None),
    "2015-sponsors": ("legacy/2015-sponsors", None),
    "past-projects": ("legacy/past-projects", None),
}

# Global CSS files already loaded in pages/index.html (via CDN or main template)
# These should not be included in per-page content
GLOBAL_CSS_PATTERNS = [
    "font-awesome",
    "css-css_xE-rWrJf",
    "css-css_YXH4gT2",
    "css-css_ikO0Dxm7",
    "css-css_ubzgGJ35",
    "css-css_NYiFQQOJ",
]

# Global JS files already loaded in pages/index.html
GLOBAL_JS_PATTERNS = [
    "js-siteimprove",
    "js-js_XexEZhbTmj",
    "js-js_jcCq6mIiUQ",
    "js-js_lYXBf5jBOE",
    "js-js_jWvMRvZ8oK",
    "js-js_Btvj6RNWy6",
    "recaptcha-api",
    "jquery",
    "userway.org",
    "siteimproveanalytics",
    "siteanalyze",
]


def extract_title(html_content):
    """Extract <title> text from HTML."""
    match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    if match:
        title = match.group(1).strip()
        for suffix in [" | School of Engineering", " | Innovate To Grow"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
        return title
    return None


def extract_page_specific_css(soup):
    """Extract CSS links and inline styles that are page-specific (not global)."""
    css_parts = []

    # Check for page-specific <link> CSS in <head>
    head = soup.find("head")
    if head:
        for link in head.find_all("link", rel="stylesheet"):
            href = link.get("href", "")
            if any(pat in href for pat in GLOBAL_CSS_PATTERNS):
                continue
            if href and not href.startswith("http"):
                css_parts.append(f'@import url("{href}");')

    return "\n".join(css_parts) if css_parts else ""


def clean_html(raw_html, filename=""):
    """
    Extract the main content from a full HTML page.

    Returns (content_html, page_specific_css, page_specific_js)
    """
    soup = BeautifulSoup(raw_html, "html.parser")

    # Extract page-specific CSS before stripping head
    page_css = extract_page_specific_css(soup)

    # Find the main content div
    main_div = soup.find("div", id="main")

    if not main_div:
        # Fallback: try role="main"
        main_div = soup.find(attrs={"role": "main"})

    if not main_div:
        # Last resort: return everything inside <body>
        body = soup.find("body")
        if body:
            # Use inner contents of <body>, not the <body> tag itself
            content_html = "".join(str(child) for child in body.children)
            content_html = content_html.strip()
            # Replace localhost:5050 references
            content_html = content_html.replace("http://localhost:5050/schedule", "/schedule")
            content_html = content_html.replace("http://localhost:5050/", "/")
            content_html = content_html.replace("http://localhost:5050", "/")
            return content_html, page_css, ""
        else:
            print(f"  WARNING: No main content found in {filename}, using raw HTML")
            return raw_html, "", ""

    # Get the inner HTML of main_div
    content_html = str(main_div)

    # Replace localhost:5050 references
    content_html = content_html.replace("http://localhost:5050/schedule", "/schedule")
    content_html = content_html.replace("http://localhost:5050/", "/")
    content_html = content_html.replace("http://localhost:5050", "/")

    return content_html, page_css, ""


def build_page_entry(slug, title, html_content, css_code="", js_code=""):
    """Build a single page entry for the manifest."""
    return {
        "export_version": "1.0",
        "export_type": "page",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "page": {
            "title": title,
            "slug": slug,
            "template_name": "",
            "meta_title": title,
            "meta_description": f"Legacy page: {title}",
            "meta_keywords": "legacy, innovate to grow, i2g",
            "og_image": "",
            "canonical_url": "",
            "meta_robots": "noindex",
            "google_site_verification": "",
            "google_structured_data": None,
        },
        "components": [
            {
                "name": f"{title} - Content",
                "component_type": "html",
                "order": 0,
                "is_enabled": True,
                "html_content": html_content,
                "css_code": css_code,
                "js_code": js_code,
                "config": {},
                "image_alt": "",
                "image_caption": "",
                "image_link": "",
                "background_image_alt": "",
                "data_source_name": None,
                "form_slug": None,
                "data_params": {},
                "refresh_interval_seconds": 0,
                "hydrate_on_client": False,
                "images": [],
            }
        ],
    }


def main():
    entries = []
    skipped = []

    for filename in sorted(os.listdir(CAPTURED_DIR)):
        if not filename.endswith(".html"):
            continue

        name = filename[:-5]

        if name not in PAGE_METADATA:
            skipped.append(name)
            continue

        slug, override_title = PAGE_METADATA[name]

        filepath = os.path.join(CAPTURED_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            raw_html = f.read()

        title = override_title or extract_title(raw_html) or name.replace("-", " ").title()

        # Clean HTML: extract main content, remove nav/footer/head
        content_html, page_css, page_js = clean_html(raw_html, filename)

        original_size = len(raw_html)
        cleaned_size = len(content_html)
        reduction = (1 - cleaned_size / original_size) * 100 if original_size > 0 else 0

        entry = build_page_entry(slug, title, content_html, page_css, page_js)
        entries.append(entry)
        print(
            f"  Added: {slug:45s} ({title}) "
            f"[{original_size:,} → {cleaned_size:,} bytes, -{reduction:.0f}%]"
        )

    if skipped:
        print(f"\nSkipped (no metadata): {skipped}")

    # Build manifest
    manifest = {
        "export_version": "2.0",
        "entries": entries,
    }

    # Write ZIP
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    zip_size = os.path.getsize(OUTPUT_ZIP)
    print(f"\nCreated: {OUTPUT_ZIP}")
    print(f"  Entries: {len(entries)}")
    print(f"  ZIP size: {zip_size:,} bytes ({zip_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
