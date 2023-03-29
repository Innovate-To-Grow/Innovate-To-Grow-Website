import asyncio
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, render_template, request, url_for, redirect, copy_current_request_context
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, RadioField
from wtforms.validators import InputRequired
from project import app, sh, wks
from project.models import event, edit_form
from project.utils.email import send_email
from project.utils.token import generate_token, confirm_token_no_expiry
from project.utils.index_helper import wks_indices, arr_indices
from project.utils.field import checkbox_get_choices
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

    wks_idx = wks_indices(wks)
    arr_idx = arr_indices(wks)

    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is None:
        return render_template("no_live_event.html")

    if request.method == "POST" and form.validate_on_submit():
        email = request.form["email"].lower()

        async def query_prim_col():
            return wks.find(email, in_column=wks_idx["Primary Email"])

        async def query_sec_col():
            return wks.find(email, in_column=wks_idx["Secondary Email"])

        async def main():
            return await asyncio.gather(query_prim_col(), query_sec_col())

        user = asyncio.run(main())
        user = user[0] if user[0] is not None else user[1] if user[1] is not None else None

        if user is None:
            subject = "I2G Membership - Complete Registration"
            token = generate_token(email)
            url = url_for("registration.complete_registration", token=token, _external=True)
            html = render_template("complete_email.html", url=url)
            send_email(email, subject, html)

            return render_template("not_registered.html")
        else:
            user = wks.row_values(user.row)

        @copy_current_request_context
        def send_instructions():
            if (user[arr_idx["Primary Verified"]] == "FALSE" and user[arr_idx["Secondary Verified"]] == "TRUE"):
                if user[arr_idx["Secondary Email"]] != "":
                    token = generate_token(user[arr_idx["Secondary Email"]])
                    event_url = url_for("events.event_register", event_name=event_obj.name, token=token, _external=True)
                    html = render_template(
                        "event_email.html",
                        first=user[arr_idx["First Name"]],
                        last=user[arr_idx["Last Name"]],
                        event_url=event_url,
                    )
                    send_email(user[arr_idx["Secondary Email"]], "I2G Membership - Event Registration", html)

            elif (user[arr_idx["Primary Verified"]] == "TRUE" and user[arr_idx["Secondary Verified"]] == "FALSE"):
                if user[arr_idx["Primary Email"]] != "":
                    token = generate_token(user[arr_idx["Primary Email"]])
                    event_url = url_for("events.event_register", event_name=event_obj.name, token=token, _external=True)
                    html = render_template(
                        "event_email.html",
                        first=user[arr_idx["First Name"]],
                        last=user[arr_idx["Last Name"]],
                        event_url=event_url,
                    )
                    send_email(user[arr_idx["Primary Email"]], "I2G Membership - Event Registration", html)

            elif (user[arr_idx["Primary Verified"]] == "FALSE" and user[arr_idx["Secondary Verified"]] == "FALSE"):
                return render_template("not_registered.html")

            else:
                if user[arr_idx["Primary Email"]] != "":
                    token = generate_token(user[arr_idx["Primary Email"]])
                    event_url = url_for("events.event_register", event_name=event_obj.name, token=token, _external=True)
                    html = render_template(
                        "event_email.html",
                        first=user[arr_idx["First Name"]],
                        last=user[arr_idx["Last Name"]],
                        event_url=event_url,
                    )
                    send_email(user[arr_idx["Primary Email"]], "I2G Membership - Event Registration", html)

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

    wks_idx = wks_indices(wks)
    arr_idx = arr_indices(wks)

    update_url = url_for("update.update_info", token=token, _external=True)

    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is None:
        return render_template("no_live_event.html")

    event_wks = sh.worksheet(event_obj.name)

    event_wks_idx = wks_indices(event_wks)
    event_arr_idx = arr_indices(event_wks)

    if email:

        async def query_prim_col():
            return wks.find(email, in_column=wks_idx["Primary Email"])

        async def query_sec_col():
            return wks.find(email, in_column=wks_idx["Secondary Email"])

        async def main():
            return await asyncio.gather(query_prim_col(), query_sec_col())

        user = asyncio.run(main())
        user = user[0] if user[0] is not None else user[1] if user[1] is not None else None
        if user is None:
            return render_template("error5.html")
        else:
            user = wks.row_values(user.row)

            if user[arr_idx["Primary Verified"]] == "FALSE" and user[arr_idx["Secondary Verified"]] == "FALSE":
                return render_template("error5.html")
    else:
        return render_template("error5.html")

    async def query_event_prim_col():
        return event_wks.find(email, in_column=event_wks_idx["Membership Primary"])

    async def query_event_sec_col():
        return event_wks.find(email, in_column=event_wks_idx["Membership Secondary"])

    async def main():
        return await asyncio.gather(query_event_prim_col(), query_event_sec_col())

    event_user = asyncio.run(main())
    event_user = event_user[0] if event_user[0] is not None else event_user[1] if event_user[1] is not None else None

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
        temp_event_user = event_wks.row_values(event_user.row)

        person["zoom_or_not"] = temp_event_user[event_arr_idx["Zoom or In-Person?"]]
        person["tickets"] = temp_event_user[event_arr_idx["Ticket Type"]]

        for question in event_obj.questions.split("\n"):
            if event_wks_idx[question] > len(temp_event_user):
                person[question] = ""
            else:
                person[question] = temp_event_user[event_arr_idx[question]]

    form = EventRegistrationForm(data=person)

    if request.method == "POST" and form.validate_on_submit():

        @copy_current_request_context
        def update_event_wks():
            cells = []

            info_fields = {}
            for row in edit_form.query.all():
                if row.field_type == "Checkbox":
                    info_fields[row.label] = " ".join(user[arr_idx[row.label]].split("\n"))
                else:
                    info_fields[row.label] = user[arr_idx[row.label]]

            event_fields = {}
            if event_obj is not None:
                event_fields["Zoom or In-Person?"] = form.zoom_or_not.data
                event_fields["Ticket Type"] = form.tickets.data

                for question in event_obj.questions.split("\n"):
                    event_fields[question] = form[question].data

            if already_registered:
                cells.append(
                    Cell(event_user.row, event_wks_idx["Last Updated"],
                         str(datetime.now().replace(second=0, microsecond=0))))
                cells.append(Cell(event_user.row, event_wks_idx["Ticket Type"], form.tickets.data))
                cells.append(Cell(event_user.row, event_wks_idx["Zoom or In-Person?"], form.zoom_or_not.data))

                for question in event_obj.questions.split("\n"):
                    cells.append(Cell(event_user.row, event_wks_idx[question], form[question].data))

                if len(cells) > 0:
                    event_wks.update_cells(cells)

                html = render_template("event_updated_email.html",
                                        update_url=update_url,
                                        first=user[arr_idx["First Name"]],
                                        last=user[arr_idx["Last Name"]],
                                        primary_email=user[arr_idx["Primary Email"]],
                                        primary_verified=user[arr_idx["Primary Verified"]],
                                        primary_subscribed=user[arr_idx["Primary Subscribed"]],
                                        secondary_email=user[arr_idx["Secondary Email"]],
                                        secondary_verified=user[arr_idx["Secondary Verified"]],
                                        secondary_subscribed=user[arr_idx["Secondary Subscribed"]],
                                        event_name=event_obj.name if event_obj is not None else None,
                                        info_fields=info_fields,
                                        event_fields=event_fields,
                                        event=event_obj,
                                        token=token)
                subject = "I2G Membership - Event Registration Updated"

            else:
                row = ["" for i in range(len(event_wks_idx))]

                row[event_arr_idx["Order"]] = int(
                    event_wks.col_values(1)[-1]) + 1 if event_wks.col_values(1)[-1].isdigit() else 1
                row[event_arr_idx["First Name"]] = user[arr_idx["First Name"]]
                row[event_arr_idx["Last Name"]] = user[arr_idx["Last Name"]]
                row[event_arr_idx["When Started"]] = str(datetime.now().replace(second=0, microsecond=0))
                row[event_arr_idx["Last Updated"]] = str(datetime.now().replace(second=0, microsecond=0))
                row[event_arr_idx["Membership Primary"]] = user[arr_idx["Primary Email"]]
                row[event_arr_idx["Membership Secondary"]] = user[arr_idx["Secondary Email"]]
                row[event_arr_idx["Ticket Type"]] = form.tickets.data
                row[event_arr_idx["Zoom or In-Person?"]] = form.zoom_or_not.data

                for question in event_obj.questions.split("\n"):
                    row[event_arr_idx[question]] = form[question].data

                event_wks.append_row(row)

                html = render_template("event_confirmed_email.html",
                                        update_url=update_url,
                                        first=user[arr_idx["First Name"]],
                                        last=user[arr_idx["Last Name"]],
                                        primary_email=user[arr_idx["Primary Email"]],
                                        primary_verified=user[arr_idx["Primary Verified"]],
                                        primary_subscribed=user[arr_idx["Primary Subscribed"]],
                                        secondary_email=user[arr_idx["Secondary Email"]],
                                        secondary_verified=user[arr_idx["Secondary Verified"]],
                                        secondary_subscribed=user[arr_idx["Secondary Subscribed"]],
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
                                first=user[arr_idx["First Name"]],
                                last=user[arr_idx["Last Name"]],
                                primary_email=user[arr_idx["Primary Email"]],
                                primary_verified=user[arr_idx["Primary Verified"]],
                                primary_subscribed=user[arr_idx["Primary Subscribed"]],
                                secondary_email=user[arr_idx["Secondary Email"]],
                                secondary_verified=user[arr_idx["Secondary Verified"]],
                                secondary_subscribed=user[arr_idx["Secondary Subscribed"]],
                                zoom_or_not=form.zoom_or_not.data,
                                tickets=form.tickets.data,
                                event_questions=event_questions)

    return render_template("event_registration.html", form=form, event=event_obj, token=token)
