from wtforms import Form, StringField, PasswordField, SubmitField, validators, TextAreaField, RadioField

class EmailForm(Form):
    subject = StringField('Subject')

    body = TextAreaField('Body')

    selection = RadioField('Send to:', choices=[('Subscribed','Subscribed Users'),('Verified','Verified Users')], default='Subscribed')

    submit = SubmitField('Send')

class LoginForm(Form):
    username = StringField("Username")

    password = PasswordField("Password")

    submit = SubmitField("Log In")