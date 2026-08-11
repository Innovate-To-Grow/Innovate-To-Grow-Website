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
