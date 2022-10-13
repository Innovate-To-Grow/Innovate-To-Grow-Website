from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField
from wtforms.validators import EqualTo, Email, InputRequired
class EmailForm(FlaskForm):
    email = StringField('Email Address', [InputRequired(' '), Email()])
    submit = SubmitField('Send')

class UpdateForm(FlaskForm):
    first_name = StringField('First Name', [InputRequired(' ')])

    last_name = StringField('Last Name', [InputRequired(' ')])

    primary_email = StringField('Primary Email Address', [InputRequired(' '), Email()])

    confirm_primary = StringField('Confirm Primary Email', [InputRequired(' '),
                                            EqualTo('primary_email', message = 'Must match primary email')])

    primary_subscribe = BooleanField('Enable Email Notifications with Primary')  

    secondary_email = StringField('Secondary Email Address', [InputRequired(' '), Email()])

    confirm_secondary = StringField('Confirm Secondary Email', [InputRequired(' '),
                                        EqualTo('secondary_email', message = 'Must match secondary email')])

    secondary_subscribe = BooleanField('Enable Email Notifications with Secondary')
    
    submit = SubmitField('Submit')
