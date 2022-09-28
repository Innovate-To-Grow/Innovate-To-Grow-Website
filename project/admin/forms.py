from wtforms import Form, StringField, SubmitField, validators, widgets, TextAreaField, RadioField

class EmailForm(Form):
    subject = StringField('Subject')

    body = TextAreaField('Body')

    selection = RadioField('Send to:', choices=[('Subscribed','Subscribed Users'),('Verified','Verified Users')], default='Subscribed')

    submit = SubmitField('Send')
    
    
