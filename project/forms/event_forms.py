from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, ValidationError
from wtforms.validators import Email, EqualTo, InputRequired

class EventRegistrationForm(FlaskForm):
    first_name = StringField("First Name", validators=[InputRequired()])
    last_name = StringField("Last Name", validators=[InputRequired()])
    email = StringField("Email", validators=[InputRequired(), Email()])
    confirm_email = StringField("Confirm Email", validators=[InputRequired(), Email(), EqualTo("email")])
    submit = SubmitField("Submit")