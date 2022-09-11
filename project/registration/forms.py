from wtforms import Form, StringField, SelectField, RadioField, IntegerField, SubmitField, validators, SelectMultipleField, widgets, ValidationError

class NotEqualTo(object):
    def __init__(self, fieldname, message=None):
        self.fieldname = fieldname
        self.message = message

    def __call__(self, form, field):
        try:
            other = form[self.fieldname]
        except KeyError:
            raise ValidationError(field.gettext("Invalid field name '%s'.") % self.fieldname)
        if field.data == other.data:
            d = {
                'other_label': hasattr(other, 'label') and other.label.text or self.fieldname,
                'other_name': self.fieldname
            }
            message = self.message
            if message is None:
                message = field.gettext('Field must not be equal to %(other_name)s.')

            raise ValidationError(message % d)

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()
    
class RegistrationForm(Form):
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
                                validators.Email(),
                                NotEqualTo('primary_email', message = 'Can not be the same email.')])
    confirm_secondary = StringField('Confirm Secondary Email',
                                [validators.InputRequired(' '),
                                validators.EqualTo('secondary_email', message = 'Must match secondary email')])
    submit = SubmitField('Submit')
    


class InformationForm(Form):
    organization = StringField('Organization *', 
                                [validators.InputRequired(' ')])

    phonenumber = StringField('Phone Number *', 
                                [validators.InputRequired(' ')])

    titlerole = StringField('Title/Role *', 
                                [validators.Optional(strip_whitespace=True)])
    submit = SubmitField('Submit')
