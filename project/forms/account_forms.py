from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, ValidationError
from wtforms.validators import Email, EqualTo, InputRequired

class LoginForm(FlaskForm):
    email = StringField('Email Address', [InputRequired(' '), Email()])
    password = PasswordField('Password', [InputRequired(' ')])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    email = StringField('Email Address', [InputRequired(' '), Email()])
    password = PasswordField('Password', [InputRequired(' ')])
    confirm_password = PasswordField('Confirm Password', [InputRequired(' '), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Submit')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email Address', [InputRequired(' '), Email()])
    submit = SubmitField('Submit')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', [InputRequired(' ')])
    confirm_password = PasswordField('Confirm New Password', [InputRequired(' '), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Submit')
    