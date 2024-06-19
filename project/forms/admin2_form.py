from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, SelectField, PasswordField
from wtforms.validators import DataRequired, Length, EqualTo,InputRequired,Email
from wtforms import IntegerField


class add_Registration(FlaskForm):
    First_Name = StringField('First_Name', validators=[DataRequired()])
    Last_Name = StringField('Last_Name', validators=[DataRequired()]) 
    Email = StringField('Email', validators=[DataRequired()]) 
    Secondary_Email = StringField('Secondary_Email', validators=[DataRequired()])
    Organization = StringField('Organization', validators=[DataRequired()])
    Role = StringField('Role', validators=[DataRequired()])
    submit = SubmitField('Input')

class LoginForm(FlaskForm):
    email = StringField("Email", [InputRequired(" "), Email()])
    password = PasswordField("Password", [InputRequired(" ")])
    submit = SubmitField("Log In")

class add_Judge(FlaskForm):
    User_ID = SelectField('Select Judge', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Add Judge')

class add_Parking(FlaskForm):
    Name = StringField('Name', validators=[DataRequired()])
    X_Location = StringField('X_Location', validators=[DataRequired()]) 
    Y_Location = StringField('Y_Location', validators=[DataRequired()]) 
    submit = SubmitField('Input')
    
class add_Project(FlaskForm):
    Project_Name = StringField('Project_Name', validators=[DataRequired()])
    Project_Des = StringField('Project_Des', validators=[DataRequired()]) 
    Mentor = StringField('Mentor', validators=[DataRequired()]) 
    Mentor1 = StringField('Mentor1', validators=[DataRequired()]) 
    Mentor2 = StringField('Mentor2', validators=[DataRequired()])
    submit = SubmitField('Input')

class add_Room(FlaskForm):
    Name = StringField('Name', validators=[DataRequired()])
    Project__ID  = SelectField('Select Project', coerce=int, validators=[DataRequired()])
    Link = StringField('Link', validators=[DataRequired()]) 
    submit = SubmitField('Input')

class add_Event(FlaskForm):
    Project_ID  = SelectField('Select Project', coerce=int, validators=[DataRequired()])
    Room_ID  = SelectField('Select Room', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Input')

class RemoveUserForm(FlaskForm):
    User_ID = SelectField('Select User', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Delete User')    
    
class add_EventJudge(FlaskForm):
    Judge_ID  = SelectField('Select Judge', coerce=int, validators=[DataRequired()])
    Event_ID  = SelectField('Select Event', coerce=int, validators=[DataRequired()])
    Link = StringField('Link', validators=[DataRequired()])
    Link2 = StringField('Link2', validators=[DataRequired()])
    Link3 = StringField('Link3', validators=[DataRequired()])
    Link4 = StringField('Link4', validators=[DataRequired()])
    submit = SubmitField('Input')