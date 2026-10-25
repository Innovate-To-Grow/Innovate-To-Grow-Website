"""CSS and design-token services.

All of the site's CSS ships with the frontend bundle (pages/src); these services cover what the
backend still owns.

- ``tokens``: renders ``SiteSettings.design_tokens`` as a ``:root { --itg-* }`` block,
  refusing values that could break out of it.
- ``theme``: the /layout/theme.css body: the cascade layer order, the tokens (``itg.tokens``)
  and ``SiteSettings.custom_css`` (``itg.overrides``).
- ``custom_css``: the checks custom CSS must pass before it is saved.
- ``revisions``: saved versions of the custom CSS.
- ``audit``: lists the CSS classes that stored CMS content uses and what styles each one,
  built on ``css_selectors`` (which classes a stylesheet defines, via tinycss2) and
  ``frontend_graph`` (which frontend CSS files the entry bundle loads on every page).

The request path imports ``tokens`` and ``theme``; ``audit`` is reached from the
``audit_css_classes`` management command.
"""
