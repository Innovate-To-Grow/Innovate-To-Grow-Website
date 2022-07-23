from tkinter.tix import Select
from wtforms import Form, StringField, SelectField, RadioField, IntegerField, SubmitField, validators, SelectMultipleField, validators, SelectMultipleField, widgets

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class EmailForm(Form):
    email = StringField('Email Address', [validators.InputRequired(' '), validators.Email()])
    submit = SubmitField('Send')

class UpdateForm(Form):
    first_name = StringField('First Name', [validators.InputRequired(' ')])
    last_name = StringField('Last Name', [validators.InputRequired(' ')])
    primary_email = StringField('Primary Email Address', 
                                [validators.InputRequired(' '),
                                validators.Email()])
    confirm_primary = StringField('Confirm Primary Email',
                                [validators.InputRequired(' '),
                                validators.EqualTo('primary_email', message = 'Must match primary email')])
    secondary_email = StringField('Secondary Email Address', 
                                [validators.InputRequired(' '),
                                validators.Email()])
    confirm_secondary = StringField('Confirm Secondary Email',
                                [validators.InputRequired(' '),
                                validators.EqualTo('secondary_email', message = 'Must match secondary email')])
    organization = StringField('Organization *', 
                                [validators.InputRequired(' ')])
    phonenumber = StringField('Phone Number *', 
                                [validators.InputRequired(' ')])
    titlerole = StringField('Title/Role *', 
                                [validators.Optional(strip_whitespace=True)])

    submit = SubmitField('Submit')
