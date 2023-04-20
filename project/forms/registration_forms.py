from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, ValidationError
from wtforms.validators import Email, EqualTo, InputRequired


class NotEqualTo(object):

    def __init__(self, fieldname, message=None):
        self.fieldname = fieldname
        self.message = message

    def __call__(self, form, field):
        try:
            other = form[self.fieldname]
        except KeyError:
            raise ValidationError(field.gettext("Invalid field name '%s'.") % self.fieldname)
        if field.data.lower() == other.data.lower():
            d = {
                'other_label': hasattr(other, 'label') and other.label.text or self.fieldname,
                'other_name': self.fieldname
            }
            message = self.message
            if message is None:
                message = field.gettext('Field must not be equal to %(other_name)s.')

            raise ValidationError(message % d)


class RegistrationForm(FlaskForm):
    first_name = StringField('First Name', [InputRequired(' ')])

    last_name = StringField('Last Name', [InputRequired(' ')])

    primary_email = StringField('Primary Email Address', [InputRequired(' '), Email()])

    confirm_primary = StringField(
        'Confirm Primary Email',
        [InputRequired(' '), EqualTo('primary_email', message='Must match primary email')])

    secondary_email = StringField(
        'Secondary Email Address',
        [InputRequired(' '),
         Email(), NotEqualTo('primary_email', message='Can not be the same email')])

    confirm_secondary = StringField(
        'Confirm Secondary Email',
        [InputRequired(' '), EqualTo('secondary_email', message='Must match secondary email')])

    submit = SubmitField('Submit')
