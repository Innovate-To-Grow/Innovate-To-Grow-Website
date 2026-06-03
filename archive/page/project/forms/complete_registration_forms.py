from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    HiddenField,
    StringField,
    SubmitField,
    ValidationError,
)
from wtforms.validators import Email, EqualTo, InputRequired, Optional

from project.forms.registration_forms import NotEqualTo


class ConditionalRequiredIfFieldProvided:
    """Makes a field required only if another field has data."""

    def __init__(self, other_field_name, message=None):
        self.other_field_name = other_field_name
        self.message = (
                message or f"This field is required when {other_field_name} is provided"
        )

    def __call__(self, form, field):
        other_field = getattr(form, self.other_field_name)
        if other_field.data and not field.data:
            raise ValidationError(self.message)


class CompleteRegistrationForm(FlaskForm):
    first_name = StringField("First Name", validators=[InputRequired()])
    last_name = StringField("Last Name", validators=[InputRequired()])
    primary_email = StringField("Primary Email Address", [InputRequired(" "), Email()])
    confirm_primary = StringField(
        "Confirm Primary Email",
        [
            InputRequired(" "),
            EqualTo("primary_email", message="Must match primary email"),
        ],
    )

    primary_subscribe = BooleanField(
        "Subscribe to Email News \n(You can opt out anytime)", default=True
    )
    secondary_email = StringField(
        "Secondary Email Address",
        [
            Optional(),
            Email(),
            NotEqualTo("primary_email", message="Cannot be the same as primary email"),
        ],
    )
    confirm_secondary = StringField(
        "Confirm Secondary Email",
        [
            ConditionalRequiredIfFieldProvided(
                "secondary_email", "Please confirm your secondary email"
            ),
            EqualTo("secondary_email", message="Must match secondary email"),
        ],
    )

    secondary_subscribe = BooleanField(
        "Subscribe to Email News \n(You can opt out anytime)", default=True
    )

    # Hidden field kept for template/back-compat; always "1" (two-email registration).
    registration_method = HiddenField("Registration Method")

    submit = SubmitField("Submit")

    def validate(self, extra_validators=None):
        """Custom form validation. Phone-based registration has been removed."""
        # This runs all the individual field validators first.
        if not super().validate(extra_validators=extra_validators):
            return False

        self.registration_method.data = "1"
        return True
