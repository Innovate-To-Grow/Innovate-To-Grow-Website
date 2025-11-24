from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, SelectField, HiddenField, ValidationError
from wtforms.validators import EqualTo, Email, InputRequired, Optional
from project.forms.registration_forms import NotEqualTo


class ConditionalRequiredIfFieldProvided:
    """Makes a field required only if another field has data."""
    def __init__(self, other_field_name, message=None):
        self.other_field_name = other_field_name
        self.message = message or f'This field is required when {other_field_name} is provided'

    def __call__(self, form, field):
        other_field = getattr(form, self.other_field_name)
        if other_field.data and not field.data:
            raise ValidationError(self.message)


class CompleteRegistrationForm(FlaskForm):
    first_name = StringField("First Name", validators=[InputRequired()])
    last_name = StringField("Last Name", validators=[InputRequired()])
    primary_email = StringField('Primary Email Address', [InputRequired(' '), Email()])
    confirm_primary = StringField(
        'Confirm Primary Email',
        [InputRequired(' '), EqualTo('primary_email', message='Must match primary email')])
    primary_subscribe = BooleanField("Subscribe to Email Notifications", default=True)
    secondary_email = StringField(
        'Secondary Email Address',
        [
            Optional(),
            Email(), 
            NotEqualTo('primary_email', message='Cannot be the same as primary email')
        ])
    confirm_secondary = StringField(
        'Confirm Secondary Email',
        [
            ConditionalRequiredIfFieldProvided('secondary_email', 'Please confirm your secondary email'),
            EqualTo('secondary_email', message='Must match secondary email')
        ])
    secondary_subscribe = BooleanField("Subscribe to Email Notifications", default=True)
    
    # Phone number fields
    country_code = SelectField('Country Code', choices=[
        ("", "No Phone"),
        ('+1', '+1 (USA)'),
        ('+52', '+52 (Mexico)'),
        ('+44', '+44 (UK)'),
        ('+61', '+61 (Australia)'),
        ('+81', '+81 (Japan)'),
        ('+91', '+91 (India)'),
        ('+49', '+49 (Germany)'),
        ('+33', '+33 (France)'),
        ('+86', '+86 (China)'),
    ])
    
    phone_number = StringField("Phone Number", [Optional()])
    
    phone_subscribe = BooleanField("Subscribe to messages from I2G")
    
    confirm_phone_number = StringField(
        "Confirm Phone Number",
        [
            ConditionalRequiredIfFieldProvided('phone_number', 'Please confirm your phone number'),
            EqualTo('phone_number', message='Must match phone number')
        ]
    )
    
    # Hidden field to store registration method
    # 1 = two emails, 2 = email and phone, 3 = all three methods
    registration_method = HiddenField('Registration Method')
    
    submit = SubmitField('Submit')

    def validate(self, extra_validators=None):
        """Custom form validation to ensure secondary contact and phone-country consistency."""
        # This runs all the individual field validators first.
        if not super().validate(extra_validators=extra_validators):
            return False

        success = True

        # Rule 1: At least one secondary contact is required.
        if not self.secondary_email.data and not self.phone_number.data:
            error_msg = 'At least one secondary contact method is required'
            self.secondary_email.errors.append(error_msg)
            self.phone_number.errors.append(error_msg)
            success = False

        phone_provided = self.phone_number.data
        country_code_provided = self.country_code.data # This is falsy if "" (No Phone) is selected

        # Rule 2: If phone is provided, country code must be too.
        if phone_provided and not country_code_provided:
            self.country_code.errors.append('A country code is required when a phone number is provided.')
            success = False

        # Rule 3: If country code is provided, phone must be too.
        if country_code_provided and not phone_provided:
            self.phone_number.errors.append('A phone number is required when a country code is selected.')
            success = False

        # If validation passed so far, set the registration method.
        if success:
            if self.secondary_email.data and self.phone_number.data:
                self.registration_method.data = '3'
            elif self.secondary_email.data:
                self.registration_method.data = '1'
            elif self.phone_number.data:
                self.registration_method.data = '2'

        return success
