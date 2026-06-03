from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import Email, InputRequired


class EmailForm(FlaskForm):
    email = StringField("Email Address", [InputRequired(" "), Email()])

    submit = SubmitField("Email Me a Link!")
