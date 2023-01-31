from gspread.cell import Cell
from flask import Blueprint, render_template, request
from wtforms import StringField, RadioField
from wtforms.validators import InputRequired
from project import app, db, sh
from project.models import event
from project.forms.event_forms import EventRegistrationForm
import sys

events_blueprint = Blueprint("events", __name__, template_folder="../templates/membership/events", url_prefix=app.config["URL_PREFIX"])

@events_blueprint.route("/event-registration", methods=["GET", "POST"])
def event_register():
    event_obj = db.session.query(event).order_by(event.id.desc()).first()
    print(event_obj.questions.split("\n"), file=sys.stderr)
    
    setattr(EventRegistrationForm, "tickets", RadioField("Ticket Type", choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")], validators=[InputRequired()]))
    
    for question in event_obj.questions.split("\n"):
        setattr(EventRegistrationForm, question, StringField(question, validators=[InputRequired()]))

    form = EventRegistrationForm()

    if request.method == "POST":
        wks = sh.worksheet(event_obj.name)

        search = wks.find(form.email.data)
        if search is not None:
            return render_template("already_registered.html")

        row = [form.first_name.data, form.last_name.data, form.email.data, form.tickets.data]
        wks.append_row(row)

        cells = []
        for question in event_obj.questions.split("\n"):
            row = wks.find(form.email.data).row
            cells.append(Cell(row, wks.find(question).col, getattr(form, question).data))
        
        wks.update_cells(cells)

        return render_template("successfully_registered.html")

    return render_template("event_registration.html", form=form, name=event_obj.name, description=event_obj.description, date=event_obj.date, time=event_obj.time, location=event_obj.location)
