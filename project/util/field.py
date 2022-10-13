from wtforms import StringField, SelectField, SelectMultipleField
from wtforms.validators import InputRequired, StopValidation
from wtforms.widgets import ListWidget, CheckboxInput

class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(html_tag='ol', prefix_label=False)
    option_widget = CheckboxInput()

class MultiCheckboxAtLeastOne():
    def __init__(self, message=None):
        if not message:
            message = 'At least one option must be selected.'
        self.message = message

    def __call__(self, form, field):
        if len(field.data) == 0:
            raise StopValidation(self.message)

def get_field(field): 
    if field.field_type == "text":
        if field.required:
            return StringField(field.label, [InputRequired(' ')])
        else:
            return StringField(field.label)

    if field.field_type == "dropdown":
        if field.required:
            return SelectField(field.label, [InputRequired(' ')], choices=dropdown_get_choices(field.options))
        else:
            return SelectField(field.label, choices=dropdown_get_choices(field.options))

    if field.field_type == "checkbox":
        if field.required:
            return MultiCheckboxField(field.label, [MultiCheckboxAtLeastOne()],
                                      choices=checkbox_get_choices(field.options), coerce=int)
        else:
            return MultiCheckboxField(field.label, choices=checkbox_get_choices(field.options), coerce=int)


def dropdown_get_choices(options):
    return options.split(" ; ")


def checkbox_get_choices(options):
    choices = []
    temp = options.split(" ; ")
    for n in range(len(temp)):
        choices.append((n, temp[n]))

    return choices 