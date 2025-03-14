from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, ValidationError
from wtforms.validators import Email, EqualTo, InputRequired

class PasswordComplexity(object):
    def __init__(self, message=None):
        self.message = message
    
    def __call__(self, form, field):
        valid, text = self.complex_password(field.data)
        if not valid:
            message = self.message
            if message is None:
                message = text
            raise ValidationError(message)
        
    def complex_password(self, password):
        #UNCOMMENT THIS LINE TO DISABLE PASSWORD COMPLEXITY
        #return True, None 

        if len(password) < 8:
            return False, "Password must be at least 8 characters"
        if not any(c.isupper() for c in password):
            return False, "Password must contain at least 1 uppercase letter"
        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least 1 number"
        if not any(c in "`~!@#$%^&*()-_=+[{]}|;:,<.>/?'\\\"" for c in password): #escape \ and " characters
            return False, "Password must contain at least 1 special character"
        return True, None


class LoginForm(FlaskForm):
    email = StringField('Email Address', [InputRequired(' '), Email()])
    password = PasswordField('Password', [InputRequired(' ')])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    email = StringField('Email Address', [InputRequired(' '), Email()])
    password = PasswordField('Password', [InputRequired(' '), PasswordComplexity()])
    confirm_password = PasswordField('Confirm Password', [InputRequired(' '), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Sign Up')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email Address', [InputRequired(' '), Email()])
    submit = SubmitField('Send Email')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', [InputRequired(' '), PasswordComplexity()])
    confirm_password = PasswordField('Confirm New Password', [InputRequired(' '), EqualTo('password', message='Passwords do not match')])
    submit = SubmitField('Update Password')
    