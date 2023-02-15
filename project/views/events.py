from gspread.cell import Cell
from flask import Blueprint, render_template, request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, RadioField, BooleanField
from wtforms.validators import Email, EqualTo, InputRequired
from project import app, sh, wks
from project.models import event
from project.forms.registration_forms import NotEqualTo

events_blueprint = Blueprint("events",
                             __name__,
                             template_folder="../templates/membership/events",
                             url_prefix=app.config["URL_PREFIX"])


@events_blueprint.route("/event-registration", methods=["GET", "POST"])
def event_register():

    class EventRegistrationForm(FlaskForm):
        first_name = StringField("First Name", validators=[InputRequired()])
        last_name = StringField("Last Name", validators=[InputRequired()])
        email = StringField("Email", validators=[InputRequired(), Email()])
        confirm_email = StringField("Confirm Email",
                                    validators=[InputRequired(),
                                                Email(),
                                                EqualTo("email", "Emails must match")])
        also_member = BooleanField("Do you also want to register for I2G membership?", default=True)
        secondary = StringField("Secondary Email", validators=[NotEqualTo("email", "Emails must be different")])
        confirm_secondary = StringField("Confirm Secondary Email",
                                        validators=[EqualTo("secondary", "Emails must match")])
        zoom_or_not = RadioField("Zoom or In-Person?",
                                 choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
                                 validators=[InputRequired()])
        submit = SubmitField("Submit")

    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    setattr(
        EventRegistrationForm, "tickets",
        RadioField("Ticket Type",
                   choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                   validators=[InputRequired()]))

    for question in event_obj.questions.split("\n"):
        setattr(EventRegistrationForm, question, StringField(question, validators=[InputRequired()]))

    form = EventRegistrationForm()

    if request.method == "POST" and form.validate_on_submit():
        event_wks = sh.worksheet(event_obj.name)

        email = request.form["email"].lower()

        search = event_wks.find(email)
        if search is not None:
            return render_template("already_registered.html")

        row = [
            int(event_wks.col_values(1)[-1]) + 1, form.first_name.data, form.last_name.data, email, form.zoom_or_not.data,
            form.tickets.data
        ]
        event_wks.append_row(row)

        cells = []
        for question in event_obj.questions.split("\n"):
            row = event_wks.find(email).row
            cells.append(Cell(row, event_wks.find(question).col, getattr(form, question).data))

        event_wks.update_cells(cells)

        return render_template("successfully_registered.html")

    return render_template("event_registration.html",
                           form=form,
                           name=event_obj.name,
                           description=event_obj.description,
                           date=event_obj.date,
                           time=event_obj.time,
                           location=event_obj.location)

@events_blueprint.route("/event-update/<token>", methods=["GET", "POST"])
def event_update(token):
    return "Event Update"
