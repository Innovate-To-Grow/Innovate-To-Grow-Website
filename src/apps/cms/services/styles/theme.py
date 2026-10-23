"""The /layout/theme.css body: the cascade layer order, the design tokens and the custom CSS.

All of the site's CSS ships with the frontend bundle, in cascade layers
(pages/src/styles/layers.css). This sheet carries what admins edit in Site Settings: the
design tokens in ``itg.tokens``, above the bundle's fallback tokens, and the custom CSS in
``itg.overrides``, above every bundled rule. It is linked before the bundle, so it opens with
the full layer order statement: the first statement that names the layers fixes their order.
"""

import hashlib

from .tokens import render_tokens_css

LAYER_ORDER = ("itg.defaults", "itg.tokens", "itg.base", "itg.components", "itg.overrides", "itg.page")
LAYER_ORDER_STATEMENT = f"@layer {', '.join(LAYER_ORDER)};"


def build_theme_css(site_settings) -> str:
    parts = [LAYER_ORDER_STATEMENT]
    tokens = render_tokens_css(site_settings.design_tokens)
    if tokens:
        parts.append("@layer itg.tokens {\n" + tokens.rstrip("\n") + "\n}")
    custom = (site_settings.custom_css or "").strip()
    if custom:
        # Last, so a brace an editor left open can only swallow its own rules.
        parts.append("@layer itg.overrides {\n" + custom + "\n}")
    return "\n\n".join(parts) + "\n"


def theme_etag(css: str) -> str:
    return '"' + hashlib.sha256(css.encode("utf-8")).hexdigest()[:32] + '"'
