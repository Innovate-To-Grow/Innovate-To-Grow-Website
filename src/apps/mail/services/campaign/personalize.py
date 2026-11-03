"""Simple placeholder-based email personalization."""


def personalize(template, context):
    """
    Replace ``{{key}}`` and ``{{ key }}`` placeholders in *template* with
    values from *context*.  Unknown placeholders are left untouched.

    Uses plain string replacement (not Django templates) to avoid template
    injection from admin-authored HTML.
    """
    result = template
    for key, value in context.items():
        replacement = value or ""
        result = result.replace("{{" + key + "}}", replacement)
        result = result.replace("{{ " + key + " }}", replacement)
    return result


def uses_placeholder(key, *templates) -> bool:
    """Whether any of *templates* contains the ``{{key}}`` or ``{{ key }}`` placeholder."""
    return any(f"{{{{{key}}}}}" in template or f"{{{{ {key} }}}}" in template for template in templates if template)


def recipients_without_login_link(campaign, recipients) -> int:
    """How many *recipients* get the sign-in page for ``{{login_link}}`` (no member account); 0 when it is unused."""
    if not uses_placeholder("login_link", campaign.subject, campaign.body):
        return 0
    return sum(1 for recipient in recipients if not recipient["member_id"])
