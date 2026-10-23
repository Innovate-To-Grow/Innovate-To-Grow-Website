"""One field per design token for the Site Settings form, instead of the raw token JSON.

The fields follow the default token set (``default_design_tokens``). Tokens stored under other
keys or groups are kept as they are, shown read-only. A blank field means the default value.
"""

import copy
import re

from django import forms

from apps.cms.models.content.layout.site_settings import default_design_tokens
from apps.cms.services.styles.tokens import MAX_TOKEN_VALUE_LENGTH, is_safe_token_value, token_variable_name

GROUP_TITLES = {
    "colors": "Colors",
    "typography": "Typography",
    "typography_mobile": "Typography on phones",
    "layout": "Layout",
    "borders": "Borders",
    "effects": "Effects",
}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
TEXT_INPUT_CLASS = (
    "border border-base-200 bg-white font-medium placeholder-base-400 rounded-default shadow-xs "
    "text-font-default-light text-sm focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600 "
    "h-[38px] w-full max-w-2xl block"
)


def token_field_name(group, key):
    return f"token__{group}__{key}"


def reset_field_name(group):
    return f"reset__{group}"


def _text_widget():
    return forms.TextInput(attrs={"class": TEXT_INPUT_CLASS, "spellcheck": "false"})


def _color_widget():
    return forms.TextInput(attrs={"type": "color", "class": "h-[38px] w-24 rounded-default border border-base-200"})


def token_form_fields():
    """Declared fields for every default token, plus one "reset group" box per group."""
    fields = {}
    for group, values in default_design_tokens().items():
        for key, default in values.items():
            fields[token_field_name(group, key)] = forms.CharField(
                label=token_variable_name(group, key),
                required=False,
                max_length=MAX_TOKEN_VALUE_LENGTH,
                help_text=f"Default: {default}",
                widget=_color_widget() if HEX_COLOR.match(default) else _text_widget(),
            )
        fields[reset_field_name(group)] = forms.BooleanField(
            label=f"Reset {GROUP_TITLES.get(group, group).lower()} to the defaults", required=False
        )
    return fields


def token_fieldsets():
    """Admin fieldsets for the token fields, one collapsed section per group."""
    return [
        (
            f"Design tokens: {GROUP_TITLES.get(group, group)}",
            {
                "fields": [token_field_name(group, key) for key in values] + [reset_field_name(group)],
                "classes": ["collapse"],
            },
        )
        for group, values in default_design_tokens().items()
    ]


def unknown_tokens(tokens):
    """Stored tokens the form has no field for (other groups or keys)."""
    defaults = default_design_tokens()
    if not isinstance(tokens, dict):
        return {}
    extra = {}
    for group, values in tokens.items():
        if group not in defaults or not isinstance(values, dict):
            extra[group] = values
            continue
        others = {key: value for key, value in values.items() if key not in defaults[group]}
        if others:
            extra[group] = others
    return extra


class DesignTokenFormMixin:
    """Fills the token fields from the instance and folds them back into ``design_tokens``."""

    def init_token_fields(self):
        stored = self.instance.design_tokens if isinstance(self.instance.design_tokens, dict) else {}
        for group, values in default_design_tokens().items():
            current = stored.get(group) if isinstance(stored.get(group), dict) else {}
            for key, default in values.items():
                field = self.fields[token_field_name(group, key)]
                value = str(current.get(key, default))
                field.initial = value
                if HEX_COLOR.match(default) and not HEX_COLOR.match(value):
                    # A colour picker can only show #rrggbb; anything else would be overwritten.
                    field.widget = _text_widget()

    def tokens_from_cleaned_data(self):
        stored = self.instance.design_tokens if isinstance(self.instance.design_tokens, dict) else {}
        tokens = copy.deepcopy(stored)
        for group, values in default_design_tokens().items():
            if self.cleaned_data.get(reset_field_name(group)):
                tokens[group] = dict(values)
                continue
            current = tokens.get(group) if isinstance(tokens.get(group), dict) else {}
            tokens[group] = current
            for key, default in values.items():
                name = token_field_name(group, key)
                text = (self.cleaned_data.get(name) or "").strip() or default
                if is_safe_token_value(text):
                    current[key] = text
                else:
                    self.add_error(name, "Not a safe CSS value: no ; braces < > \\ or comments, balanced quotes.")
        return tokens
