from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, RadioField
from wtforms.validators import InputRequired

class EmailForm(FlaskForm):
    subject = StringField('Subject')

    body = TextAreaField('Body')

    selection = RadioField('Send to:', choices=[('Subscribed', 'Subscribed Users'),('Verified', 'Verified Users')], default='Subscribed')

    submit = SubmitField('Send')

class LoginForm(FlaskForm):
    username = StringField("Username", [InputRequired(' ')])

    password = PasswordField("Password", [InputRequired(' ')])

    submit = SubmitField("Log In")