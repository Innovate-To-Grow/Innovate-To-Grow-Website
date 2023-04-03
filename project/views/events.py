import asyncio
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, render_template, request, url_for, redirect, copy_current_request_context
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, RadioField
from wtforms.validators import InputRequired
from project import app, sh, wks, get_wks_records, get_wks_columns
from project.models import event, edit_form
from project.utils.email import send_email
from project.utils.token import generate_token, confirm_token_no_expiry
from project.forms.update_forms import EmailForm

events_blueprint = Blueprint("events",
                             __name__,
                             template_folder="../templates/membership/events",
                             url_prefix=app.config["URL_PREFIX"])


@events_blueprint.route("/events", methods=["GET", "POST"])
def event_redirect():
    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is None:
        return render_template("no_live_event.html")

    return redirect(url_for("events.enter_email", event_name=event_obj.name))


@events_blueprint.route("/events/<event_name>", methods=["GET", "POST"])
def enter_email(event_name):
    form = EmailForm()

    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is None:
        return render_template("no_live_event.html")

    if request.method == "POST" and form.validate_on_submit():
        wks_records = get_wks_records(wks)
        
        email = request.form["email"].lower()

        async def query_prim_col():
            return [row for row in wks_records if row["Primary Email"] == email]

        async def query_sec_col():
            return [row for row in wks_records if row["Secondary Email"] == email]

        async def main():
            return await asyncio.gather(query_prim_col(), query_sec_col())

        user = asyncio.run(main())
        user = user[0][0] if user[0] else user[1][0] if user[1] else None

        if user is None:
            subject = "I2G Membership - Complete Registration"
            token = generate_token(email)
            url = url_for("registration.complete_registration", token=token, _external=True)
            html = render_template("complete_email.html", url=url)
            send_email(email, subject, html)

            return render_template("not_registered.html")
        

        @copy_current_request_context
        def send_instructions():
            if (user["Primary Verified"] == "FALSE" and user["Secondary Verified"] == "TRUE"):
                if user["Primary Email"] != "":
                    token = generate_token(user["Primary Email"])
                    confirm_url = url_for("registration.confirm", token=token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        confirm_url=confirm_url,
                    )
                    send_email(user["Primary Email"], app.config["VERIF_SUBJECT"], html)

                if user["Secondary Email"] != "":
                    token = generate_token(user["Secondary Email"])
                    event_url = url_for("events.event_register", event_name=event_obj.name, token=token, _external=True)
                    html = render_template(
                        "event_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        event_url=event_url,
                    )
                    send_email(user["Secondary Email"], "I2G Membership - Event Registration", html)


            elif (user["Primary Verified"] == "TRUE" and user["Secondary Verified"] == "FALSE"):
                if user["Primary Email"] != "":
                    token = generate_token(user["Primary Email"])
                    event_url = url_for("events.event_register", event_name=event_obj.name, token=token, _external=True)
                    html = render_template(
                        "event_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        event_url=event_url,
                    )
                    send_email(user["Primary Email"], "I2G Membership - Event Registration", html)

                if user["Secondary Email"] != "":
                    token = generate_token(user["Secondary Email"])
                    confirm_url = url_for("registration.confirm", token=token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        confirm_url=confirm_url,
                    )
                    send_email(user["Secondary Email"], app.config["VERIF_SUBJECT"], html)


            elif (user["Primary Verified"] == "FALSE" and user["Secondary Verified"] == "FALSE"):
                return render_template("not_registered.html")

            else:
                if user["Primary Email"] != "":
                    token = generate_token(user["Primary Email"])
                    event_url = url_for("events.event_register", event_name=event_obj.name, token=token, _external=True)
                    html = render_template(
                        "event_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        event_url=event_url,
                    )
                    send_email(user["Primary Email"], "I2G Membership - Event Registration", html)

                # if user[arr_idx["Secondary Email"]] != "":
                #     token = generate_token(user[arr_idx["Secondary Email"]])
                #     event_url = url_for("events.event_register", event_name=event_obj.name, token=token, _external=True)
                #     html = render_template(
                #         "event_email.html",
                #         first=user[arr_idx["First Name"]],
                #         last=user[arr_idx["Last Name"]],
                #         event_url=event_url,
                #     )
                #     send_email(user[arr_idx["Secondary Email"]], "I2G Membership - Event Registration", html)

        Thread(target=send_instructions).start()

        return render_template("event_instructions_sent.html", event=event_obj)

    return render_template("event_enter_form.html", form=form)


@events_blueprint.route("/event-registration/<event_name>/<token>", methods=["GET", "POST"])
def event_register(event_name, token):
    email = confirm_token_no_expiry(token)

    wks_records = get_wks_records(wks)
    wks_columns = get_wks_columns(wks)

    update_url = url_for("update.update_info", token=token, _external=True)

    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is None:
        return render_template("no_live_event.html")

    event_wks = sh.worksheet(event_obj.name)

    event_wks_records = get_wks_records(event_wks)
    event_wks_columns = get_wks_columns(event_wks)

    if email:

        async def query_prim_col():
            return [row for row in wks_records if row["Primary Email"] == email]

        async def query_sec_col():
            return [row for row in wks_records if row["Secondary Email"] == email]

        async def main():
            return await asyncio.gather(query_prim_col(), query_sec_col())

        user = asyncio.run(main())
        user = user[0][0] if user[0] else user[1][0] if user[1] else None
        if user is None:
            return render_template("error5.html")
        else:
            if user["Primary Verified"] == "FALSE" and user["Secondary Verified"] == "FALSE":
                return render_template("error5.html")
    else:
        return render_template("error5.html")

    async def query_event_prim_col():
        return [row for row in event_wks_records if row["Membership Primary"] == email]

    async def query_event_sec_col():
        return [row for row in event_wks_records if row["Membership Secondary"] == email]

    async def main():
        return await asyncio.gather(query_event_prim_col(), query_event_sec_col())

    event_user = asyncio.run(main())
    event_user = event_user[0][0] if event_user[0] else event_user[1][0] if event_user[1] else None

    already_registered = False

    if event_user is not None:
        already_registered = True

    class EventRegistrationForm(FlaskForm):
        zoom_or_not = RadioField("Zoom or In-Person?",
                                 choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
                                 validators=[InputRequired()])
        submit = SubmitField("Submit")

    setattr(
        EventRegistrationForm, "tickets",
        RadioField("Ticket Type",
                   choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                   validators=[InputRequired()]))

    for question in event_obj.questions.split("\n"):
        setattr(EventRegistrationForm, question, StringField(question, validators=[InputRequired()]))

    person = {}

    if already_registered:
        person["zoom_or_not"] = event_user["Zoom or In-Person?"]
        person["tickets"] = event_user["Ticket Type"]

        for question in event_obj.questions.split("\n"):
            if event_wks_columns[question] > len(event_user):
                person[question] = ""
            else:
                person[question] = event_user[question]

    form = EventRegistrationForm(data=person)

    if request.method == "POST" and form.validate_on_submit():
        event_wks_columns = get_wks_columns(event_wks)

        @copy_current_request_context
        def update_event_wks():
            cells = []

            info_fields = {}
            for row in edit_form.query.all():
                if row.field_type == "Checkbox":
                    info_fields[row.label] = " ".join(user[row.label].split("\n"))
                else:
                    if wks_columns[row.label] > len(user):
                        info_fields[row.label] = ""
                    else:
                        info_fields[row.label] = user[row.label]

            event_fields = {}
            if event_obj is not None:
                event_fields["Zoom or In-Person?"] = form.zoom_or_not.data
                event_fields["Ticket Type"] = form.tickets.data

                for question in event_obj.questions.split("\n"):
                    event_fields[question] = form[question].data

            if already_registered:
                cells.append(
                    Cell(event_user["Row"], event_wks_columns["Last Updated"],
                         str(datetime.now().replace(second=0, microsecond=0))))
                cells.append(Cell(event_user["Row"], event_wks_columns["Ticket Type"], form.tickets.data))
                cells.append(Cell(event_user["Row"], event_wks_columns["Zoom or In-Person?"], form.zoom_or_not.data))

                for question in event_obj.questions.split("\n"):
                    cells.append(Cell(event_user["Row"], event_wks_columns[question], form[question].data))

                if len(cells) > 0:
                    event_wks.update_cells(cells)

                html = render_template("event_updated_email.html",
                                        update_url=update_url,
                                        first=user["First Name"],
                                        last=user["Last Name"],
                                        primary_email=user["Primary Email"],
                                        primary_verified=user["Primary Verified"],
                                        primary_subscribed=user["Primary Subscribed"],
                                        secondary_email=user["Secondary Email"],
                                        secondary_verified=user["Secondary Verified"],
                                        secondary_subscribed=user["Secondary Subscribed"],
                                        event_name=event_obj.name if event_obj is not None else None,
                                        info_fields=info_fields,
                                        event_fields=event_fields,
                                        event=event_obj,
                                        token=token)
                subject = "I2G Membership - Event Registration Updated"

            else:
                row = ["" for i in range(len(event_wks_columns))]

                row[event_wks_columns["Order"] - 1] = int(
                    event_wks.col_values(1)[-1]) + 1 if event_wks.col_values(1)[-1].isdigit() else 1
                row[event_wks_columns["First Name"] - 1] = user["First Name"]
                row[event_wks_columns["Last Name"] - 1] = user["Last Name"]
                row[event_wks_columns["When Started"] - 1] = str(datetime.now().replace(second=0, microsecond=0))
                row[event_wks_columns["Last Updated"] - 1] = str(datetime.now().replace(second=0, microsecond=0))
                row[event_wks_columns["Membership Primary"] - 1] = user["Primary Email"]
                row[event_wks_columns["Membership Secondary"] - 1] = user["Secondary Email"]
                row[event_wks_columns["Ticket Type"] - 1] = form.tickets.data
                row[event_wks_columns["Zoom or In-Person?"] - 1] = form.zoom_or_not.data

                for question in event_obj.questions.split("\n"):
                    row[event_wks_columns[question] - 1] = form[question].data

                event_wks.append_row(row)

                html = render_template("event_confirmed_email.html",
                                        update_url=update_url,
                                        first=user["First Name"],
                                        last=user["Last Name"],
                                        primary_email=user["Primary Email"],
                                        primary_verified=user["Primary Verified"],
                                        primary_subscribed=user["Primary Subscribed"],
                                        secondary_email=user["Secondary Email"],
                                        secondary_verified=user["Secondary Verified"],
                                        secondary_subscribed=user["Secondary Subscribed"],
                                        info_fields=info_fields,
                                        event_name=event_obj.name if event_obj is not None else None,
                                        event_fields=event_fields,
                                        event=event_obj,
                                        token=token)
                subject = "I2G Membership - Event Registration Confirmed"

            send_email(email, subject, html)

        Thread(target=update_event_wks).start()

        event_questions = {}

        for question in event_obj.questions.split("\n"):
            event_questions[question] = form[question].data

        return render_template("successfully_registered.html", event=event_obj, token=token,
                                update_url=update_url,
                                first=user["First Name"],
                                last=user["Last Name"],
                                primary_email=user["Primary Email"],
                                primary_verified=user["Primary Verified"],
                                primary_subscribed=user["Primary Subscribed"],
                                secondary_email=user["Secondary Email"],
                                secondary_verified=user["Secondary Verified"],
                                secondary_subscribed=user["Secondary Subscribed"],
                                zoom_or_not=form.zoom_or_not.data,
                                tickets=form.tickets.data,
                                event_questions=event_questions)

    return render_template("event_registration.html", form=form, event=event_obj, token=token)
