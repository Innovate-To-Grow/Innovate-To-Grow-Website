"""
OTP (One-Time Password) Forms

Forms for handling phone number verification via SMS OTP codes.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import InputRequired, Length, Regexp


class OTPForm(FlaskForm):
    """
    Form used to receive the user's one-time password from Twilio.
    
    This form captures the 6-digit OTP code that users receive via SMS
    and validates the format before submission.
    """
    otp = StringField(
        '',
        validators=[
            InputRequired(message="Please enter the verification code"),
            Length(min=6, max=6, message="Verification code must be 6 digits"),
            Regexp(regex="^[0-9]{6}$", message="Verification code must contain only numbers")
        ],
        render_kw={
            "placeholder": "123456",
            "class": "form-control",
            "maxlength": "6",
            "pattern": "[0-9]{6}",
            "autocomplete": "one-time-code",
            "inputmode": "numeric"
        }
    )

    submit = SubmitField(
        'Verify Phone Number',
        render_kw={
            "class": "btn btn-primary btn-block"
        }
    )
