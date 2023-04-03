from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, RadioField
from wtforms.validators import InputRequired, Email, EqualTo


class EmailForm(FlaskForm):
    subject = StringField("Subject", [InputRequired(" ")])

    body = TextAreaField("Body", [InputRequired(" ")])

    selection = RadioField("Send to:",
                           choices=[("Admin", "Administrators"), ("Event", "Event Attendees"), ("Subscribed", "Subscribed Users")],
                           default="Admin")

    submit = SubmitField("Send")


class LoginForm(FlaskForm):
    email = StringField("Email", [InputRequired(" "), Email()])

    password = PasswordField("Password", [InputRequired(" ")])

    submit = SubmitField("Log In")


class NewAdmin(FlaskForm):
    email = StringField("Email Address", [InputRequired(" "), Email()])

    role = RadioField("Role", choices=[("admin", "admin"), ("superadmin", "superadmin")], default="admin")

    submit = SubmitField("Send")


class RegisterAdmin(FlaskForm):
    first_name = StringField("First Name", [InputRequired(" ")])

    last_name = StringField("Last Name", [InputRequired(" ")])

    password = PasswordField("Password", [InputRequired(" ")])

    confirm_password = PasswordField(
        "Confirm Password",
        [InputRequired(" "), EqualTo("password", message="Passwords must match")])
        
    submit = SubmitField("Submit")