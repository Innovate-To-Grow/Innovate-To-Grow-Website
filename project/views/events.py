import asyncio, time
from datetime import datetime
from threading import Thread

from gspread.cell import Cell
from flask import Blueprint, render_template, request, url_for, redirect, copy_current_request_context, abort
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField
from wtforms.validators import EqualTo, Email, InputRequired

from project import app, sh, wks, logs, tz, get_wks_records, get_wks_columns
from project.models import event, edit_form
from project.utils.email import send_email
from project.utils.dynamic_fields import get_field, checkbox_get_choices
from project.utils.token import generate_token, confirm_token
from project.utils.event_utils import make_sure
from project.forms.registration_forms import NotEqualTo
from project.forms.update_forms import EmailForm
from project.services.logging_service import Logger


events_blueprint = Blueprint("events",
                             __name__,
                             template_folder="../templates/membership/events",
                             url_prefix=app.config["URL_PREFIX"])

logger = Logger()


@events_blueprint.route("/events", methods=["GET", "POST"])
def event_redirect():
    event_obj: event | None = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is None:
        return render_template("no_live_event.html")

    return redirect(url_for("events.enter_email", event_name=event_obj.name.replace(" ", "-")))


@events_blueprint.route("/events/<event_name>", methods=["GET", "POST"])
def enter_email(event_name):
    form = EmailForm()

    event_obj: event | None = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is None:
        return render_template("no_live_event.html")

    event_obj = event.query.filter_by(name=event_name.replace("-", " "), live=True).order_by(event.id.desc()).first()

    if event_obj is None:
        abort(404)

    if request.method == "POST" and form.validate_on_submit():

        wks_records = get_wks_records(wks)

        email = form.email.data.lower()
        path = f"/events/{event_name}"

        Thread(target=logger.log_email_submission, args=(path, email)).start()

        async def query_prim_col():
            return [row for row in wks_records if row["Primary Email"] == email]

        async def query_sec_col():
            return [row for row in wks_records if row["Secondary Email"] == email]

        async def main():
            return await asyncio.gather(query_prim_col(), query_sec_col())

        user = asyncio.run(main())
        user = user[0][0] if user[0] else user[1][0] if user[1] else None

        if user is None:
            subject = "I2G Membership - Complete Your Registration"
            token = generate_token(email)
            url = url_for("registration.complete_registration", token=token, _external=True)
            html = render_template("complete_email.html", email=email, url=url, live_event=True if event_obj else False)
            send_email(email, subject, html)

            return render_template("instructions_sent.html")


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
                    event_url = url_for("events.event_register", event_name=event_obj.name.replace(" ", "-"), token=token, _external=True)
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
                    event_url = url_for("events.event_register", event_name=event_obj.name.replace(" ", "-"), token=token, _external=True)
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

                    token = generate_token(user["Secondary Email"])
                    confirm_url = url_for("registration.confirm", token=token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        confirm_url=confirm_url,
                    )
                    send_email(user["Secondary Email"], app.config["VERIF_SUBJECT"], html)


            else:
                if user["Primary Email"] != "":
                    token = generate_token(user["Primary Email"])
                    event_url = url_for("events.event_register", event_name=event_obj.name.replace(" ", "-"), token=token, _external=True)
                    html = render_template(
                        "event_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        event_url=event_url,
                    )
                    send_email(user["Primary Email"], "I2G Membership - Event Registration", html)

        Thread(target=send_instructions).start()

        return render_template("instructions_sent.html", event=event_obj)

    return render_template("event_enter_form.html", form=form)


@events_blueprint.route("/event-registration/<event_name>/<token>", methods=["GET", "POST"])
def event_register(event_name, token):
    user = None
    email = confirm_token(token, app.config["EVENT_TOKEN_EXPIRATION"])

    wks_records = get_wks_records(wks)
    wks_columns = get_wks_columns(wks)

    event_cells = []
    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    event_url = None
    update_url = url_for("update.update_info", token=token, _external=True)

    if event_obj is None:
        return render_template("no_live_event.html")
    else:
        event_wks = sh.worksheet(event_obj.name)
        event_wks_records = get_wks_records(event_wks)
        event_wks_columns = get_wks_columns(event_wks)
        event_url = url_for("events.event_register", event_name=event_obj.name.replace(" ", "-"), token=token, _external=True)

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
            return render_template("error2.html")

    if user is None:
        return redirect(url_for("events.enter_email", event_name=event_obj.name.replace(" ", "-"), _external=True))

    class UpdateForm(FlaskForm):
        first_name = StringField("First Name", [InputRequired(" ")])
        last_name = StringField("Last Name", [InputRequired(" ")])
        primary_email = StringField("Primary Email Address", [InputRequired(" "), Email()])
        confirm_primary = StringField(
            "Confirm Primary Email",
            [InputRequired(" "), EqualTo("primary_email", message="Must match primary email")])
        primary_subscribe = BooleanField("Enable Email Notifications")
        secondary_email = StringField(
            "Secondary Email Address",
            [InputRequired(" "),
             Email(), NotEqualTo("primary_email", message="Can not be the same email")])
        confirm_secondary = StringField(
            "Confirm Secondary Email",
            [InputRequired(" "), EqualTo("secondary_email", message="Must match secondary email")])
        secondary_subscribe = BooleanField("Enable Email Notifications")
        submit = SubmitField("Submit")

    for row in edit_form.query.all():
        setattr(UpdateForm, row.label, get_field(row))

    primary_temp = False
    if user["Primary Subscribed"] == "TRUE":
        primary_temp = True

    secondary_temp = False
    if user["Secondary Subscribed"] == "TRUE":
        secondary_temp = True

    person = {
        "first_name": user["First Name"],
        "last_name": user["Last Name"],
        "primary_email": user["Primary Email"],
        "confirm_primary": user["Primary Email"],
        "secondary_email": user["Secondary Email"],
        "confirm_secondary": user["Secondary Email"],
        "primary_subscribe": primary_temp,
        "secondary_subscribe": secondary_temp,
    }

    for row in edit_form.query.all():
        if wks_columns[row.label] > len(user):
            person.update([(row.label, "")])
        else:
            if row.field_type == "Checkbox":
                keys = []
                if user[row.label] != "":
                    choices = checkbox_get_choices(row.options)
                    for val in user[row.label].split("\n"):
                        key = [key for key, v in choices if v == val][0]
                        keys.append(key)
                person.update([(row.label, keys)])
            else:
                person.update([(row.label, user[row.label])])

    if event_obj is not None:
        async def query_event_prim_col():
            return [row for row in event_wks_records if row["Membership Primary"] == email]

        async def query_event_sec_col():
            return [row for row in event_wks_records if row["Membership Secondary"] == email]

        async def main():
            return await asyncio.gather(query_event_prim_col(), query_event_sec_col())

        event_user = asyncio.run(main())
        event_user = event_user[0][0] if event_user[0] else event_user[1][0] if event_user[1] else None

        if event_user is not None:
            register_event_label = "Update " + event_obj.name + " Registration"
        else:
            register_event_label = "Register for " + event_obj.name

        setattr(UpdateForm, "register_event", BooleanField(register_event_label, default=True))
        # setattr(
        #     UpdateForm, "event_zoom_or_not",
        #     RadioField("Will you attend on Zoom or In-Person?",
        #                choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
        #                validators=[InputRequired(" ")]))
        setattr(
            UpdateForm, "event_tickets",
            RadioField("Ticket Type",
                       choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                       validators=[InputRequired(" ")]))

        for question in event_obj.questions.split("\n"):
            setattr(UpdateForm, "event_" + question, StringField(question, validators=[InputRequired(" ")]))

        if event_user is not None:
            # person["event_zoom_or_not"] = event_user["Will you attend on Zoom or In-Person?"]
            person["event_tickets"] = event_user["Ticket Type"]

            for question in event_obj.questions.split("\n"):
                if event_wks_columns[question] > len(event_user):
                    person["event_" + question] = ""
                else:
                    person["event_" + question] = event_user[question]

    form = UpdateForm(data=person)
    form.register_event.render_kw = {"disabled": True}


    if request.method == "POST" and form.validate_on_submit():

        # LOG STUFF #
        path = f"/event-registration/{event_name}/{token}"
        first_name = form.first_name.data
        last_name = form.last_name.data
        primary_email = form.primary_email.data
        secondary_email = form.secondary_email.data
        Thread(target=logger.log_event_register, args=(path, first_name, last_name, primary_email, secondary_email)).start()

        wks_records = get_wks_records(wks)
        wks_columns = get_wks_columns(wks)

        if event_obj is not None:
            event_wks_records = get_wks_records(event_wks)
            event_wks_columns = get_wks_columns(event_wks)

        cell_find = [row for row in wks_records if row["Primary Email"] == email]
        if not cell_find:
            cell_find = [row for row in wks_records if row["Secondary Email"] == email]

        row_find = cell_find[0]["Row"]

        cells = []

        update_allowed = True

        prim_email = form.primary_email.data.lower()
        sec_email = form.secondary_email.data.lower()


        # Use the refactored validation function
        update_allowed, cells_to_update, emails_to_send = make_sure(
            update_allowed, wks_records, row_find, prim_email, sec_email
        )

        # Convert cells_to_update to Cell objects and add to cells list
        for cell_update in cells_to_update:
            cells.append(Cell(cell_update["row"], wks_columns[cell_update["column"]], cell_update["value"]))

            # Handle event worksheet updates for cleared emails
            if event_obj is not None:
                # Find which email is being cleared from the worksheet
                cleared_email = None
                for record in wks_records:
                    if record["Row"] == cell_update["row"]:
                        cleared_email = record[cell_update["column"]]
                        break

                if cleared_email:
                    if cell_update["column"] == "Primary Email":
                        event_user = [row for row in event_wks_records if row["Membership Primary"] == cleared_email]
                        column_name = "Membership Primary"
                    else:  # Secondary Email
                        event_user = [row for row in event_wks_records if row["Membership Secondary"] == cleared_email]
                        column_name = "Membership Secondary"

                    if event_user:
                        event_cells.append(Cell(event_user[0]["Row"], event_wks_columns[column_name], ""))

        # Send notification emails
        for email_to_send in emails_to_send:
            if email_to_send["type"] == "deletion_notice":
                html = render_template("deleting_email.html",
                                       first=email_to_send["user_first_name"],
                                       last=email_to_send["user_last_name"],
                                       email=email_to_send["deleted_email"])
                thread = Thread(
                    target=send_email,
                    args=[email_to_send["to"], app.config["REMOVE_SUBJECT"], html])
                thread.start()

        # Update worksheets
        if len(cells) > 0:
            wks.update_cells(cells)
        if len(event_cells) > 0:
            event_wks.update_cells(event_cells)

        cells.clear()
        event_cells.clear()

        if not update_allowed:
            return render_template("error4.html")

        else:
            swap = False

            primary_verified = user["Primary Verified"]
            if form.primary_subscribe.data:
                primary_subscribed = "TRUE"
            else:
                primary_subscribed = "FALSE"

            secondary_verified = user["Secondary Verified"]
            if form.secondary_subscribe.data:
                secondary_subscribed = "TRUE"
            else:
                secondary_subscribed = "FALSE"

            if (user["Primary Email"] == sec_email and user["Secondary Email"] == prim_email):
                swap = True
                primary_verified = user["Secondary Verified"]
                primary_subscribed = user["Secondary Subscribed"]
                secondary_verified = user["Primary Verified"]
                secondary_subscribed = user["Primary Subscribed"]

            elif user["Primary Email"] == sec_email:
                swap = True
                primary_verified = "FALSE"
                primary_subscribed = "FALSE"
                secondary_verified = user["Primary Verified"]
                secondary_subscribed = user["Primary Subscribed"]

            elif user["Secondary Email"] == prim_email:
                swap = True
                primary_verified = user["Secondary Verified"]
                primary_subscribed = user["Secondary Subscribed"]
                secondary_verified = "FALSE"
                secondary_subscribed = "FALSE"

            if user["Primary Email"] != prim_email and not swap:
                primary_verified = "FALSE"
                primary_subscribed = "FALSE"

            if user["Secondary Email"] != sec_email and not swap:
                secondary_verified = "FALSE"
                secondary_subscribed = "FALSE"

            info_fields = {}
            for row in edit_form.query.all():
                field = form[row.label]
                if row.field_type == "Checkbox":
                    vals = []
                    choices = checkbox_get_choices(row.options)
                    for key in field.data:
                        vals.append(choices[int(key)][1])
                    info_fields[row.label] = " ".join(vals)
                else:
                    if wks_columns[row.label] > len(user):
                        info_fields[row.label] = ""
                    else:
                        info_fields[row.label] = field.data

            event_fields = {}
            if event_obj is not None:
                # event_fields["Will you attend on Zoom or In-Person?"] = form.event_zoom_or_not.data
                event_fields["Ticket Type"] = form.event_tickets.data

                for question in event_obj.questions.split("\n"):
                    if event_user is not None:
                        if event_wks_columns[question] > len(event_user):
                            event_fields[question] = ""
                        else:
                            event_fields[question] = form["event_" + question].data
                    else:
                        event_fields[question] = form["event_" + question].data

            @copy_current_request_context
            def can_update(user):
                swap = False
                sent_to_prim = False
                sent_to_sec = False

                def prim_expiry_timer():
                    time.sleep(app.config["EXPIRY_TIMER"])
                    wks_records = get_wks_records(wks)
                    wks_columns = get_wks_columns(wks)
                    row = [row for row in wks_records if row["Primary Email"] == prim_email]
                    if row:
                        row = row[0]
                        if row["Primary Verified"] == "FALSE":
                            wks.update_cell(row["Row"], wks_columns["Primary Expired"], "TRUE")

                def sec_expiry_timer():
                    time.sleep(app.config["EXPIRY_TIMER"])
                    wks_records = get_wks_records(wks)
                    wks_columns = get_wks_columns(wks)
                    row = [row for row in wks_records if row["Secondary Email"] == sec_email]
                    if row:
                        row = row[0]
                        if row["Secondary Verified"] == "FALSE":
                            wks.update_cell(row["Row"], wks_columns["Secondary Expired"], "TRUE")

                if (user["Primary Email"] == sec_email and user["Secondary Email"] == prim_email):
                    swap = True
                    cells.append(Cell(
                        row_find,
                        wks_columns["Primary Verified"],
                        user["Secondary Verified"],
                    ))
                    cells.append(Cell(
                        row_find,
                        wks_columns["Secondary Verified"],
                        user["Primary Verified"],
                    ))

                    cells.append(Cell(
                        row_find,
                        wks_columns["Primary Expired"],
                        user["Secondary Expired"],
                    ))
                    cells.append(Cell(
                        row_find,
                        wks_columns["Secondary Expired"],
                        user["Primary Expired"],
                    ))

                    cells.append(Cell(
                        row_find,
                        wks_columns["Primary Bounced"],
                        user["Secondary Bounced"],
                    ))
                    cells.append(Cell(
                        row_find,
                        wks_columns["Secondary Bounced"],
                        user["Primary Bounced"],
                    ))

                # primary OR secondary email are swapped...
                elif user["Primary Email"] == sec_email:
                    swap = True
                    cells.append(Cell(
                        row_find,
                        wks_columns["Secondary Verified"],
                        user["Primary Verified"],
                    ))
                    cells.append(Cell(
                        row_find,
                        wks_columns["Secondary Expired"],
                        user["Primary Expired"],
                    ))
                    cells.append(Cell(
                        row_find,
                        wks_columns["Secondary Bounced"],
                        user["Primary Bounced"],
                    ))
                    cells.append(Cell(row_find, wks_columns["Primary Verified"], "FALSE"))
                    cells.append(Cell(row_find, wks_columns["Primary Expired"], "FALSE"))
                    cells.append(Cell(row_find, wks_columns["Primary Bounced"], ""))

                    p_token = generate_token(prim_email)
                    confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        confirm_url=confirm_url,
                    )
                    send_email(prim_email, app.config["VERIF_SUBJECT"], html)
                    sent_to_prim = True

                    thread = Thread(target=prim_expiry_timer)
                    thread.start()

                elif user["Secondary Email"] == prim_email:
                    swap = True
                    cells.append(Cell(
                        row_find,
                        wks_columns["Primary Verified"],
                        user["Secondary Verified"],
                    ))
                    cells.append(Cell(
                        row_find,
                        wks_columns["Primary Expired"],
                        user["Secondary Expired"],
                    ))
                    cells.append(Cell(
                        row_find,
                        wks_columns["Primary Bounced"],
                        user["Secondary Bounced"],
                    ))
                    cells.append(Cell(row_find, wks_columns["Secondary Verified"], "FALSE"))
                    cells.append(Cell(row_find, wks_columns["Secondary Expired"], "FALSE"))
                    cells.append(Cell(row_find, wks_columns["Secondary Bounced"], ""))

                    s_token = generate_token(sec_email)
                    confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        confirm_url=confirm_url,
                    )
                    send_email(sec_email, app.config["VERIF_SUBJECT"], html)
                    sent_to_sec = True

                    thread = Thread(target=sec_expiry_timer)
                    thread.start()

                # changing primary to different email
                if user["Primary Email"] != prim_email and not swap:

                    if not sent_to_prim:
                        p_token = generate_token(prim_email)
                        confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                        html = render_template(
                            "verify_email.html",
                            first=user["First Name"],
                            last=user["Last Name"],
                            confirm_url=confirm_url,
                        )
                        cells.append(Cell(row_find, wks_columns["Primary Verified"], "FALSE"))
                        cells.append(Cell(row_find, wks_columns["Primary Expired"], "FALSE"))
                        cells.append(Cell(row_find, wks_columns["Primary Bounced"], ""))

                        send_email(prim_email, app.config["VERIF_SUBJECT"], html)
                        sent_to_prim = True

                        thread = Thread(target=prim_expiry_timer)
                        thread.start()

                # changing secondary to different email
                if user["Secondary Email"] != sec_email and not swap:

                    if not sent_to_sec:
                        s_token = generate_token(sec_email)
                        confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                        html = render_template(
                            "verify_email.html",
                            first=user["First Name"],
                            last=user["Last Name"],
                            confirm_url=confirm_url,
                        )
                        cells.append(Cell(row_find, wks_columns["Secondary Verified"], "FALSE"))
                        cells.append(Cell(row_find, wks_columns["Secondary Expired"], "FALSE"))
                        cells.append(Cell(row_find, wks_columns["Secondary Bounced"], ""))

                        send_email(sec_email, app.config["VERIF_SUBJECT"], html)
                        sent_to_sec = True

                        thread = Thread(target=sec_expiry_timer)
                        thread.start()

                cells.append(Cell(row_find, wks_columns["First Name"], form.first_name.data))
                cells.append(Cell(row_find, wks_columns["Last Name"], form.last_name.data))
                cells.append(Cell(row_find, wks_columns["Primary Email"], prim_email))
                cells.append(Cell(row_find, wks_columns["Secondary Email"], sec_email))

                if event_obj is not None:
                    if event_user is not None:
                        event_cells.append(Cell(event_user["Row"], event_wks_columns["First Name"], form.first_name.data))
                        event_cells.append(Cell(event_user["Row"], event_wks_columns["Last Name"], form.last_name.data))
                        event_cells.append(Cell(event_user["Row"], event_wks_columns["Membership Primary"], prim_email))
                        event_cells.append(Cell(event_user["Row"], event_wks_columns["Membership Secondary"], sec_email))

                for row in edit_form.query.all():
                    if row.field_type == "Checkbox":
                        vals = []
                        choices = checkbox_get_choices(row.options)
                        for key in field.data:
                            vals.append(choices[int(key)][1])
                        cells.append(Cell(row_find, wks_columns[row.label], "\n".join(vals)))
                    else:
                        cells.append(Cell(row_find, wks_columns[row.label], field.data))

                if len(cells) > 0:
                    wks.update_cells(cells)

                cells.clear()

                wks_records = wks.get_all_records()
                user = [row for row in wks_records if row["Primary Email"] == prim_email and row["Secondary Email"] == sec_email][0]

                if user["Primary Verified"] == "FALSE":
                    cells.append(Cell(row_find, wks_columns["Primary Subscribed"], "FALSE"))
                    if not sent_to_prim:
                        p_token = generate_token(prim_email)
                        confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                        html = render_template(
                            "verify_email.html",
                            first=user["First Name"],
                            last=user["Last Name"],
                            confirm_url=confirm_url,
                        )
                        send_email(prim_email, app.config["VERIF_SUBJECT"], html)

                if user["Secondary Verified"] == "FALSE":
                    cells.append(Cell(row_find, wks_columns["Secondary Subscribed"], "FALSE"))
                    if not sent_to_sec:
                        s_token = generate_token(sec_email)
                        confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                        html = render_template(
                            "verify_email.html",
                            first=user["First Name"],
                            last=user["Last Name"],
                            confirm_url=confirm_url,
                        )
                        send_email(sec_email, app.config["VERIF_SUBJECT"], html)

                if user["Primary Verified"] == "TRUE":
                    cells.append(Cell(
                        row_find,
                        wks_columns["Primary Subscribed"],
                        form.primary_subscribe.data,
                    ))

                if user["Secondary Verified"] == "TRUE":
                    cells.append(Cell(
                        row_find,
                        wks_columns["Secondary Subscribed"],
                        form.secondary_subscribe.data,
                    ))

                cells.append(
                    Cell(
                        row_find,
                        wks_columns["Last Updated"],
                        str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")),
                    ))

                cells.append(Cell(row_find, wks_columns["Info Completed"], "TRUE"))

                if event_obj is not None:
                    if event_user is not None:
                        event_cells.append(
                            Cell(event_user["Row"], event_wks_columns["Last Updated"],
                                    str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))))
                        # event_cells.append(
                        #     Cell(event_user["Row"], event_wks_columns["Will you attend on Zoom or In-Person?"], form.event_zoom_or_not.data))
                        event_cells.append(
                            Cell(event_user["Row"], event_wks_columns["Ticket Type"], form.event_tickets.data))

                        for question in event_obj.questions.split("\n"):
                            event_cells.append(
                                Cell(event_user["Row"], event_wks_columns[question], form["event_" + question].data))

                    else:
                        row = ["" for i in range(len(event_wks.row_values(1)))]

                        row[event_wks_columns["Order"] - 1] = int(
                            event_wks.col_values(1)[-1]) + 1 if event_wks.col_values(1)[-1].isdigit() else 1
                        row[event_wks_columns["First Name"] - 1] = user["First Name"]
                        row[event_wks_columns["Last Name"] - 1] = user["Last Name"]
                        row[event_wks_columns["When Started"] - 1] = str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))
                        row[event_wks_columns["Last Updated"] - 1] = str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))
                        row[event_wks_columns["Membership Primary"] - 1] = user["Primary Email"]
                        row[event_wks_columns["Membership Secondary"] - 1] = user["Secondary Email"]
                        row[event_wks_columns["Ticket Type"] - 1] = form.event_tickets.data
                        # row[event_wks_columns["Will you attend on Zoom or In-Person?"] - 1] = form.event_zoom_or_not.data

                        for question in event_obj.questions.split("\n"):
                            row[event_wks_columns[question] - 1] = form["event_" + question].data

                        event_wks.append_row(row)

                if len(cells) > 0:
                    wks.update_cells(cells)

                if len(event_cells) > 0:
                    event_wks.update_cells(event_cells)

                wks_records = wks.get_all_records()
                user = [row for row in wks_records if row["Primary Email"] == prim_email and row["Secondary Email"] == sec_email][0]

                subject = event_obj.name + " Registration Completed"
                html = render_template("event_receipt_email.html",
                                    event_url=event_url,
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
                                    event_fields=event_fields)

                if user["Primary Verified"] == "TRUE":
                    send_email(user["Primary Email"], subject, html)
                if user["Secondary Verified"] == "TRUE":
                    send_email(user["Secondary Email"], subject, html)

            thread = Thread(target=can_update, args=(user,))
            thread.start()

            return render_template("successfully_registered.html",
                                    event_url=event_url,
                                    update_url=update_url,
                                    first=form.first_name.data,
                                    last=form.last_name.data,
                                    primary_email=form.primary_email.data,
                                    primary_verified=primary_verified,
                                    primary_subscribed=primary_subscribed,
                                    secondary_email=form.secondary_email.data,
                                    secondary_verified=secondary_verified,
                                    secondary_subscribed=secondary_subscribed,
                                    info_fields=info_fields,
                                    event_name=event_obj.name if event_obj is not None else None,
                                    event_fields=event_fields)

    else:
        # if form.errors:
        #     print(f"errors: {form.errors}")
        return render_template("event_registration.html", form=form, token=token, event=event_obj)
