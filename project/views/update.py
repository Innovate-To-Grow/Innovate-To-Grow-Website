import asyncio, time
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, render_template, url_for, request, copy_current_request_context
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField
from wtforms.validators import EqualTo, Email, InputRequired, Optional
from project import app, sh, wks, logs, tz, get_wks_records, get_wks_columns
from project.models import edit_form, event
from project.utils.email import send_email
from project.utils.dynamic_fields import get_field, checkbox_get_choices
from project.utils.token import generate_token, confirm_token
from project.forms.registration_forms import NotEqualTo
from project.forms.update_forms import EmailForm

update_blueprint = Blueprint("update",
                             __name__,
                             template_folder="../templates/membership/update",
                             url_prefix=app.config["URL_PREFIX"])


# check the database to see if the input email has a user with a registered prim. or secon. email
@update_blueprint.route("/update", methods=["GET", "POST"])
def enter_email():
    form = EmailForm()

    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if request.method == "POST" and form.validate():
        def log_email():
            order = int(logs.col_values(1)[-1]) + 1 if logs.col_values(1)[-1].isdigit() else 1
            row = [
                order, "/update", str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")), "Email: " + form.email.data
            ]
            logs.append_row(row)

        Thread(target=log_email).start()

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
            subject = "I2G Membership - Complete Your Registration"
            token = generate_token(email)
            url = url_for("registration.complete_registration", token=token, _external=True)
            html = render_template("complete_email.html", email=email, url=url, live_event=True if event_obj else False)
            send_email(email, subject, html)

            return render_template("instructions_sent.html")


        @copy_current_request_context
        def send_instructions():
            if (user["Primary Verified"] == "FALSE" and user["Secondary Verified"] == "TRUE"):
                # send an update link to the secondary and a verification link to primary
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
                    update_url = url_for("update.update_info", token=token, _external=True)
                    html = render_template(
                        "update_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        update_url=update_url,
                    )
                    send_email(user["Secondary Email"], app.config["UPDATE_SUBJECT"], html)


            elif (user["Primary Verified"] == "TRUE" and user["Secondary Verified"] == "FALSE"):
                # send an update link to primary and verification to secondary
                if user["Primary Email"] != "":
                    token = generate_token(user["Primary Email"])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    html = render_template(
                        "update_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        update_url=update_url,
                    )
                    send_email(user["Primary Email"], app.config["UPDATE_SUBJECT"], html)

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
                # user is in db, but not verified. send them links to verify both.
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
                    update_url = url_for("update.update_info", token=token, _external=True)
                    html = render_template(
                        "update_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        update_url=update_url,
                    )
                    send_email(user["Primary Email"], app.config["UPDATE_SUBJECT"], html)

                if user["Secondary Email"] != "":
                    token = generate_token(user["Secondary Email"])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    html = render_template(
                        "update_email.html",
                        first=user["First Name"],
                        last=user["Last Name"],
                        update_url=update_url,
                    )
                    send_email(user["Secondary Email"], app.config["UPDATE_SUBJECT"], html)

        thread = Thread(target=send_instructions)
        thread.start()

        return render_template("instructions_sent.html")

    else:
        return render_template("enter_form.html", form=form)


@update_blueprint.route("/update/<token>", methods=["GET", "POST"])
def update_info(token):
    email = confirm_token(token, None)

    wks_records = get_wks_records(wks)
    wks_columns = get_wks_columns(wks)

    event_cells = []
    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    event_url = None
    update_url = url_for("update.update_info", token=token, _external=True)

    if event_obj is not None:
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
        
    else:
        return render_template("error2.html")

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
            register_event_label = "Update " + event_obj.name + " registration?"
        else:
            register_event_label = "Also register for " + event_obj.name + "?"

        setattr(UpdateForm, "register_event", BooleanField(register_event_label))
        setattr(
            UpdateForm, "event_zoom_or_not",
            RadioField("Will you attend on Zoom or In-Person?",
                       choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
                       validators=[Optional()]))
        setattr(
            UpdateForm, "event_tickets",
            RadioField("Ticket Type",
                       choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                       validators=[Optional()]))

        for question in event_obj.questions.split("\n"):
            setattr(UpdateForm, "event_" + question, StringField(question))

        if event_user is not None:
            person["register_event"] = True
            person["event_zoom_or_not"] = event_user["Will you attend on Zoom or In-Person?"]
            person["event_tickets"] = event_user["Ticket Type"]

            for question in event_obj.questions.split("\n"):
                if event_wks_columns[question] > len(event_user):
                    person["event_" + question] = ""
                else:
                    person["event_" + question] = event_user[question]

    form = UpdateForm(data=person)

    if request.method == "POST" and form.validate_on_submit():
        def log_update():
            order = int(logs.col_values(1)[-1]) + 1 if logs.col_values(1)[-1].isdigit() else 1
            row = [
                order, "/update/<token>", str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")), "First Name: " + form.first_name.data,
                "Last Name: " + form.last_name.data, "Primary Email: " + form.primary_email.data, "Secondary Email: " + form.secondary_email.data
            ]
            logs.append_row(row)

        Thread(target=log_update).start()

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

        global can_update
        can_update = True

        prim_email = request.form["primary_email"].lower()
        sec_email = request.form["secondary_email"].lower()


        async def search_prim_in_prim_col():
            user_prim1 = [row for row in wks_records if row["Primary Email"] == prim_email]
            if user_prim1:
                user_prim1 = user_prim1[0]
                row_prim1 = user_prim1["Row"]
            else:
                return 

            if user_prim1 and row_prim1 != row_find:
                if user_prim1["Primary Expired"] == "FALSE":
                    global can_update
                    can_update = False
                elif user_prim1["Primary Expired"] == "TRUE":
                    cells.append(Cell(row_prim1, wks_columns["Primary Email"], ""))

                    if event_obj is not None:
                        event_user = [row for row in event_wks_records if row["Membership Primary"] == prim_email]
                        if event_user:
                            event_cells.append(Cell(event_user[0]["Row"], event_wks_columns["Membership Primary"], ""))

                    if user_prim1["Secondary Email"] != "" and user_prim1["Secondary Verified"] == "TRUE":
                        html = render_template("deleting_email.html",
                                               first=user_prim1["First Name"],
                                               last=user_prim1["Last Name"],
                                               email=user_prim1["Primary Email"])
                        thread = Thread(
                            target=send_email,
                            args=[user_prim1["Secondary Email"], app.config["REMOVE_SUBJECT"], html])
                        thread.start()


        async def search_prim_in_sec_col():
            user_prim2 = [row for row in wks_records if row["Secondary Email"] == prim_email]
            if user_prim2:
                user_prim2 = user_prim2[0]
                row_prim2 = user_prim2["Row"]
            else:
                return

            if user_prim2 and row_prim2 != row_find:
                if user_prim2["Secondary Expired"] == "FALSE":
                    global can_update
                    can_update = False
                elif user_prim2["Secondary Expired"] == "TRUE":
                    cells.append(Cell(row_prim2, wks_columns["Secondary Email"], ""))

                    if event_obj is not None:
                        event_user = [row for row in event_wks_records if row["Membership Secondary"] == prim_email]
                        if event_user:
                            event_cells.append(Cell(event_user[0]["Row"], event_wks_columns["Membership Secondary"], ""))

                    if user_prim2["Primary Email"] != "" and user_prim2["Primary Verified"] == "TRUE":
                        html = render_template("deleting_email.html",
                                               first=user_prim2["First Name"],
                                               last=user_prim2["Last Name"],
                                               email=user_prim2["Secondary Email"])
                        thread = Thread(
                            target=send_email,
                            args=[user_prim2["Primary Email"], app.config["REMOVE_SUBJECT"], html])
                        thread.start()


        async def search_sec_in_prim_col():
            user_sec1 = [row for row in wks_records if row["Primary Email"] == sec_email]
            if user_sec1:
                user_sec1 = user_sec1[0]
                row_sec1 = user_sec1["Row"]
            else:
                return

            if user_sec1 and row_sec1 != row_find:
                if user_sec1["Primary Expired"] == "FALSE":
                    global can_update
                    can_update = False
                elif user_sec1["Primary Expired"] == "TRUE":
                    cells.append(Cell(row_sec1, wks_columns["Primary Email"], ""))

                    if event_obj is not None:
                        event_user = [row for row in event_wks_records if row["Membership Primary"] == sec_email]
                        if event_user:
                            event_cells.append(Cell(event_user[0]["Row"], event_wks_columns["Membership Primary"], ""))

                    if user_sec1["Secondary Email"] != "" and user_sec1["Secondary Verified"] == "TRUE":
                        html = render_template("deleting_email.html",
                                               first=user_sec1["First Name"],
                                               last=user_sec1["Last Name"],
                                               email=user_sec1["Primary Email"])
                        thread = Thread(
                            target=send_email,
                            args=[user_sec1["Secondary Email"], app.config["REMOVE_SUBJECT"], html])
                        thread.start()


        async def search_sec_in_sec_col():
            user_sec2 = [row for row in wks_records if row["Secondary Email"] == sec_email]
            if user_sec2:
                user_sec2 = user_sec2[0]
                row_sec2 = user_sec2["Row"]
            else:
                return

            if user_sec2 and row_sec2 != row_find:
                if user_sec2["Secondary Expired"] == "FALSE":
                    global can_update
                    can_update = False
                elif user_sec2["Secondary Expired"] == "TRUE":
                    cells.append(Cell(row_sec2, wks_columns["Secondary Email"], ""))

                    if event_obj is not None:
                        event_user = [row for row in event_wks_records if row["Membership Secondary"] == sec_email]
                        if event_user:
                            event_cells.append(Cell(event_user[0]["Row"], event_wks_columns["Membership Secondary"], ""))

                    if user_sec2["Primary Email"] != "" and user_sec2["Primary Verified"] == "TRUE":
                        html = render_template("deleting_email.html",
                                               first=user_sec2["First Name"],
                                               last=user_sec2["Last Name"],
                                               email=user_sec2["Secondary Email"])
                        thread = Thread(
                            target=send_email,
                            args=[user_sec2["Primary Email"], app.config["REMOVE_SUBJECT"], html])
                        thread.start()

        async def update_sheet():
            if len(cells) > 0:
                wks.update_cells(cells)

            if len(event_cells) > 0:
                event_wks.update_cells(event_cells)

        async def main():
            await asyncio.gather(search_prim_in_prim_col(), search_prim_in_sec_col(), search_sec_in_prim_col(),
                                 search_sec_in_sec_col(), update_sheet())

        asyncio.run(main())

        cells.clear()
        event_cells.clear()

        if not can_update:
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
                if row.field_type == "Checkbox":
                    vals = []
                    choices = checkbox_get_choices(row.options)
                    for key in request.form.getlist(row.label):
                        vals.append(choices[int(key)][1])
                    info_fields[row.label] = " ".join(vals)
                else:
                    if wks_columns[row.label] > len(user):
                        info_fields[row.label] = ""
                    else:
                        info_fields[row.label] = request.form[row.label]

            event_fields = {}
            if event_obj is not None:
                if form.register_event.data:
                    event_fields["Will you attend on Zoom or In-Person?"] = form.event_zoom_or_not.data
                    event_fields["Ticket Type"] = form.event_tickets.data

                    for question in event_obj.questions.split("\n"):
                        if event_user is not None:
                            if event_wks_columns[question] > len(event_user):
                                event_fields[question] = ""
                            else:
                                event_fields[question] = form["event_" + question].data
                        else:
                            event_fields[question] = form["event_" + question].data
                    
                else:
                    if event_user is not None:
                        event_fields["Will you attend on Zoom or In-Person?"] = event_user["Will you attend on Zoom or In-Person?"]
                        event_fields["Ticket Type"] = event_user["Ticket Type"]

                        for question in event_obj.questions.split("\n"):
                            if event_wks_columns[question] > len(event_user):
                                event_fields[question] = ""
                            else:
                                event_fields[question] = event_user[question]

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
                        for key in request.form.getlist(row.label):
                            vals.append(choices[int(key)][1])
                        cells.append(Cell(row_find, wks_columns[row.label], "\n".join(vals)))
                    else:
                        cells.append(Cell(row_find, wks_columns[row.label], request.form[row.label]))

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
                    if form.register_event.data:
                        if event_user is not None:
                            event_cells.append(
                                Cell(event_user["Row"], event_wks_columns["Last Updated"],
                                     str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))))
                            event_cells.append(
                                Cell(event_user["Row"], event_wks_columns["Will you attend on Zoom or In-Person?"], form.event_zoom_or_not.data))
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
                            row[event_wks_columns["Will you attend on Zoom or In-Person?"] - 1] = form.event_zoom_or_not.data

                            for question in event_obj.questions.split("\n"):
                                row[event_wks_columns[question] - 1] = form["event_" + question].data

                            event_wks.append_row(row)

                if len(cells) > 0:
                    wks.update_cells(cells)

                if len(event_cells) > 0:
                    event_wks.update_cells(event_cells)

                wks_records = wks.get_all_records()
                user = [row for row in wks_records if row["Primary Email"] == prim_email and row["Secondary Email"] == sec_email][0]

                subject = "I2G Membership Updated"
                html = render_template("update_receipt_email.html",
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
          
            return render_template("thanks_update.html",
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
        return render_template("update_form.html", form=form, token=token)
