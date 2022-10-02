from wtforms import StringField, SelectField, SelectMultipleField, validators,widgets

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

def get_field(field): 
    if field.field_type == "text": 
        return StringField(field.label, 
                           [validators.InputRequired(' ')])
    if field.field_type == "dropdown":
        return SelectField(field.label, 
                           [validators.InputRequired(' ')],
                           choices=split_options(field.options))
    if field.field_type == "checkbox":
        return MultiCheckboxField(field.label,
                                  [validators.InputRequired(' ')],
                                  choices=split_options(field.options))

def split_options(options):
    return options.split(", ")