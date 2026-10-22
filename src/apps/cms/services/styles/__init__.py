"""CSS and design-token services.

- ``tokens``: renders ``SiteSettings.design_tokens`` as the ``:root { --itg-* }`` block
  that heads the server-served stylesheet, refusing values that could break out of it.
- ``drift``: compares the ``StyleSheet`` rows of a database with the repo seed
  (``migrations/data/stylesheets.json``) and exports them for safekeeping.
- ``audit``: lists the CSS classes that stored CMS content uses and what styles each one,
  built on ``css_selectors`` (which classes a stylesheet defines, via tinycss2) and
  ``frontend_graph`` (which frontend CSS files the entry bundle loads on every page).

Only ``tokens`` is imported by the request path; the others are reached from the
``stylesheet_drift`` / ``audit_css_classes`` management commands and the Style Sheets admin.
"""
