from flask_wtf import FlaskForm
from wtforms import PasswordField, RadioField, StringField, SubmitField, TextAreaField
from wtforms.validators import Email, EqualTo, InputRequired


class EmailForm(FlaskForm):
    subject = StringField("Subject", [InputRequired(" ")])

    recip_selection = RadioField(
        "Select recipients:",
        choices=[
            ("Admin", "Administrators"),
            ("Event", "Event Attendees"),
            ("Subscribed", "Subscribed Users"),
            ("Non-Event Subscribed", "Non-Event Subscribed Users"),
            ("Verified", "Verified Users"),
        ],
        default="Admin",
    )

    email_selection = RadioField(
        "Send to:",
        choices=[
            ("Primary", "Primary Email"),
            ("Secondary", "Secondary Email"),
            ("Both", "Both Emails"),
        ],
        default="Primary",
    )

    submit = SubmitField("Send")


class ManualEmailForm(FlaskForm):
    subject = StringField("Subject", [InputRequired(" ")])
    emails = TextAreaField("Emails (separated by comma or new line)", [InputRequired(" ")])
    submit = SubmitField("Send")


class LoginForm(FlaskForm):
    email = StringField("Email", [InputRequired(" "), Email()])

    password = PasswordField("Password", [InputRequired(" ")])

    submit = SubmitField("Log In")


class NewAdmin(FlaskForm):
    email = StringField("Email Address", [InputRequired(" "), Email()])

    role = RadioField(
        "Role",
        choices=[("admin", "admin"), ("superadmin", "superadmin")],
        default="admin",
    )

    submit = SubmitField("Send")


class RegisterAdmin(FlaskForm):
    first_name = StringField("First Name", [InputRequired(" ")])

    last_name = StringField("Last Name", [InputRequired(" ")])

    password = PasswordField("Password", [InputRequired(" ")])

    confirm_password = PasswordField(
        "Confirm Password",
        [InputRequired(" "), EqualTo("password", message="Passwords must match")],
    )

    submit = SubmitField("Submit")


class ProspectForm(FlaskForm):
    """
    Form for checking prospects sheet

    Fields:
        submit (SubmitField): clicking submit will check all the rows in the prospects sheet to
        ensure they are not in the members sheet
    """

    check = SubmitField("Check")
