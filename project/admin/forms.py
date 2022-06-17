from wtforms import Form, StringField, SubmitField, validators, widgets, TextAreaField

class EmailForm(Form):
    subject = StringField('Subject')

    body = TextAreaField('Body')

    submit = SubmitField('Send')