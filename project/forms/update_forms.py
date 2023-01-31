from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, ValidationError
from wtforms.validators import EqualTo, Email, InputRequired


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


class EmailForm(FlaskForm):
    email = StringField('Email Address', [InputRequired(' '), Email()])
    submit = SubmitField('Send')
