from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, validators, BooleanField
class EmailForm(FlaskForm):
    email = StringField('Email Address', [validators.InputRequired(' '), validators.Email()])
    submit = SubmitField('Send')

class UpdateForm(FlaskForm):
    first_name = StringField('First Name', [validators.InputRequired(' ')])

    last_name = StringField('Last Name', [validators.InputRequired(' ')])

    primary_email = StringField('Primary Email Address', 
                                [validators.InputRequired(' '),
                                validators.Email()])

    confirm_primary = StringField('Confirm Primary Email',
                                [validators.InputRequired(' '),
                                validators.EqualTo('primary_email', message = 'Must match primary email')])

    primary_subscribe = BooleanField('Enable Email Notifications with Primary')  

    secondary_email = StringField('Secondary Email Address', 
                                [validators.InputRequired(' '),
                                validators.Email()])

    confirm_secondary = StringField('Confirm Secondary Email',
                                [validators.InputRequired(' '),
                                validators.EqualTo('secondary_email', message = 'Must match secondary email')])

    secondary_subscribe = BooleanField('Enable Email Notifications with Secondary')

    titlerole = StringField('Title/Role *', 
                                [validators.Optional(strip_whitespace=True)])

    organization = StringField('Organization *', 
                                [validators.InputRequired(' ')])

    phonenumber = StringField('Phone Number *', 
                                [validators.InputRequired(' ')])
                                
    submit = SubmitField('Submit')
