import asyncio, time
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, render_template, url_for, request, redirect, copy_current_request_context
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField
from wtforms.validators import EqualTo, Email, InputRequired, Optional
from project import app, sh, wks, logs, tz, get_wks_records, get_wks_columns
from project.models import edit_form, event
from project.utils.email import send_email
from project.utils.dynamic_fields import get_field, checkbox_get_choices
from project.utils.token import generate_token, confirm_token
from project.forms.registration_forms import NotEqualTo, RegistrationForm

registration_blueprint = Blueprint("registration",
                                   __name__,
                                   template_folder="../templates/membership/registration",
                                   url_prefix=app.config["URL_PREFIX"])


@registration_blueprint.route("/signup", methods=["GET", "POST"])
def register():
    form = RegistrationForm()

    cells = []
    event_cells = []

    global can_register
    can_register = True

    if request.method == "POST" and form.validate_on_submit():
        def log_registration():
            order = int(logs.col_values(1)[-1]) + 1 if logs.col_values(1)[-1].isdigit() else 1
            row = [
                order, "/register", str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")), "First Name: " + form.first_name.data, "Last Name: " + 
                form.last_name.data, "Primary Email: " + form.primary_email.data, "Secondary Email: " + form.secondary_email.data
            ]
            logs.append_row(row)

        Thread(target=log_registration).start()

        wks_records = get_wks_records(wks)
        wks_columns = get_wks_columns(wks)

        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

        if event_obj is not None:
            event_wks = sh.worksheet(event_obj.name)
            event_wks_records = get_wks_records(event_wks)
            event_wks_columns = get_wks_columns(event_wks)

        prim_email = request.form["primary_email"].lower()
        sec_email = request.form["secondary_email"].lower()


        async def search_prim_in_prim_col():
            user_prim1 = [row for row in wks_records if row["Primary Email"] == prim_email]
            if user_prim1:
                user_prim1 = user_prim1[0]
                row_prim1 = user_prim1["Row"]
            else:
                return
            
            if (user_prim1 is not None and user_prim1["Primary Expired"] == "TRUE"):
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
                    thread = Thread(target=send_email,
                                    args=(user_prim1["Secondary Email"], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_prim1 is not None and user_prim1["Primary Expired"] == "FALSE"):
                global can_register
                can_register = False
                if user_prim1["Primary Verified"] == "TRUE":
                    token = generate_token(user_prim1["Primary Email"])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_prim1["First Name"],
                        last=user_prim1["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_prim1["Primary Email"], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()


        async def search_prim_in_sec_col():
            user_prim2 = [row for row in wks_records if row["Secondary Email"] == prim_email]
            if user_prim2:
                user_prim2 = user_prim2[0]
                row_prim2 = user_prim2["Row"]
            else:
                return
            
            if (user_prim2 is not None and user_prim2["Secondary Expired"] == "TRUE"):
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
                    thread = Thread(target=send_email,
                                    args=(user_prim2["Primary Email"], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_prim2 is not None and user_prim2["Secondary Expired"] == "FALSE"):
                global can_register
                can_register = False
                if user_prim2["Secondary Verified"] == "TRUE":
                    token = generate_token(user_prim2["Secondary Email"])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_prim2["First Name"],
                        last=user_prim2["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_prim2["Secondary Email"], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()


        async def search_sec_in_prim_col():
            user_sec1 = [row for row in wks_records if row["Primary Email"] == sec_email]
            if user_sec1:
                user_sec1 = user_sec1[0]
                row_sec1 = user_sec1["Row"]
            else:
                return

            if (user_sec1 is not None and user_sec1["Primary Expired"] == "TRUE"):
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
                    thread = Thread(target=send_email,
                                    args=(user_sec1["Secondary Email"], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_sec1 is not None and user_sec1["Primary Expired"] == "FALSE"):
                global can_register
                can_register = False
                if user_sec1["Primary Verified"] == "TRUE":
                    token = generate_token(user_sec1["Primary Email"])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec1["First Name"],
                        last=user_sec1["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_sec1["Primary Email"], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()
                    

        async def search_sec_in_sec_col():
            user_sec2 = [row for row in wks_records if row["Secondary Email"] == sec_email]
            if user_sec2:
                user_sec2 = user_sec2[0]
                row_sec2 = user_sec2["Row"]
            else:
                return

            if (user_sec2 is not None and user_sec2["Secondary Expired"] == "TRUE"):
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
                    thread = Thread(target=send_email,
                                    args=(user_sec2["Primary Email"], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_sec2 is not None and user_sec2["Secondary Expired"] == "FALSE"):
                global can_register
                can_register = False
                if user_sec2["Secondary Verified"] == "TRUE":
                    token = generate_token(user_sec2["Secondary Email"])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec2["First Name"],
                        last=user_sec2["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_sec2["Secondary Email"], app.config["UPDATE_SUBJECT"],
                                          update_html))
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

        if not can_register:
            return render_template("error1.html")
        else:

            @copy_current_request_context
            def can_register():
                user = ["" for i in range(len(wks_columns))]

                user[wks_columns["Order"] - 1] = int(wks.col_values(wks_columns["Order"])[-1]) + 1 if wks.col_values(
                    wks_columns["Order"])[-1].isdigit() else 1
                user[wks_columns["First Name"] - 1] = form.first_name.data
                user[wks_columns["Last Name"] - 1] = form.last_name.data
                user[wks_columns["When Started"] - 1] = str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))
                user[wks_columns["Last Updated"] - 1] = str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))
                user[wks_columns["Primary Email"] - 1] = prim_email
                user[wks_columns["Primary Verified"] - 1] = "FALSE"
                user[wks_columns["Primary Subscribed"] - 1] = "FALSE"
                user[wks_columns["Primary Expired"] - 1] = "FALSE"
                user[wks_columns["Primary Bounced"] - 1] = ""
                user[wks_columns["Secondary Email"] - 1] = sec_email
                user[wks_columns["Secondary Verified"] - 1] = "FALSE"
                user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
                user[wks_columns["Secondary Expired"] - 1] = "FALSE"
                user[wks_columns["Secondary Bounced"] - 1] = ""
                user[wks_columns["Info Completed"] - 1] = "FALSE"
                
                wks.append_row(user)

                p_token = generate_token(prim_email)
                p_confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                p_html = render_template(
                    "verify_email.html",
                    first=form.first_name.data,
                    last=form.last_name.data,
                    confirm_url=p_confirm_url,
                )

                s_token = generate_token(sec_email)
                s_confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                s_html = render_template(
                    "verify_email.html",
                    first=form.first_name.data,
                    last=form.last_name.data,
                    confirm_url=s_confirm_url,
                )

                send_email(prim_email, app.config["VERIF_SUBJECT"], p_html)
                send_email(sec_email, app.config["VERIF_SUBJECT"], s_html)

                def expiry_timer():
                    time.sleep(app.config["EXPIRY_TIMER"])
                    wks_records = get_wks_records(wks)
                    wks_columns = get_wks_columns(wks)
                    row = [row for row in wks_records if row["Primary Email"] == prim_email]
                    if row:
                        row = row[0]
                        if row["Primary Verified"] == "FALSE":
                            wks.update_cell(row["Row"], wks_columns["Primary Expired"], "TRUE")
                        if row["Secondary Verified"] == "FALSE":
                            wks.update_cell(row["Row"], wks_columns["Secondary Expired"], "TRUE")

                thread = Thread(target=expiry_timer)
                thread.start()

            thread = Thread(target=can_register)
            thread.start()

            return render_template("instructions_sent.html")

    else:
        return render_template("register_form.html", form=form)


@registration_blueprint.route("/confirm/<token>")
def confirm(token):
    user = None
    email = confirm_token(token, app.config["VERIFY_TOKEN_EXPIRATION"])

    wks_records = get_wks_records(wks)
    wks_columns = get_wks_columns(wks)

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
            verif_key = "Primary Verified" if user["Primary Email"] == email else "Secondary Verified"

    if user is None:
        return redirect(url_for("registration.resend_page", token=token, _external=True))

    elif user[verif_key] == "TRUE" and user["Info Completed"] == "TRUE":
        return render_template("already_confirmed.html")

    else:

        def update_sheet(wks_records, wks_columns):
            user_find = [row for row in wks_records if row["Primary Email"] == email]
            if not user_find:
                user_find = [row for row in wks_records if row["Secondary Email"] == email][0]
                verified = "Secondary Verified"
                subscribed = "Secondary Subscribed"
                expired = "Secondary Expired"
                bounced = "Secondary Bounced"
            else:
                user_find = user_find[0]
                verified = "Primary Verified"
                subscribed = "Primary Subscribed"
                expired = "Primary Expired"
                bounced = "Primary Bounced"

            row_find = user_find["Row"]

            cells = []
            cells.append(Cell(row_find, wks_columns[verified], "TRUE"))
            cells.append(Cell(row_find, wks_columns[subscribed], "TRUE"))
            cells.append(Cell(row_find, wks_columns[expired], "FALSE"))
            cells.append(Cell(row_find, wks_columns[bounced], ""))

            if len(cells) > 0:
                wks.update_cells(cells)

        thread = Thread(target=update_sheet, args=(wks_records, wks_columns))
        thread.start()

        if user["Info Completed"] == "FALSE":
            return redirect(url_for("registration.info", token=token, _external=True))
        else:
            event_url = None
            update_url = url_for("update.update_info", token=token, _external=True)

            event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

            if event_obj is not None:
                event_wks = sh.worksheet(event_obj.name)
                event_wks_records = get_wks_records(event_wks)
                event_wks_columns = get_wks_columns(event_wks)
                event_url = url_for("events.event_register", event_name=event_obj.name.replace(" ", "-"), token=token, _external=True)

                async def query_event_prim_col():
                    return [row for row in event_wks_records if row["Membership Primary"] == email]

                async def query_event_sec_col():
                    return [row for row in event_wks_records if row["Membership Secondary"] == email]

                async def main():
                    return await asyncio.gather(query_event_prim_col(), query_event_sec_col())

                event_user = asyncio.run(main())
                event_user = event_user[0][0] if event_user[0] else event_user[1][0] if event_user[1] else None

            if verif_key == "Primary Verified":
                primary_verified = "TRUE"
                secondary_verified = user["Secondary Verified"]
                primary_subscribed = "TRUE"
                secondary_subscribed = user["Secondary Subscribed"]
            else:
                primary_verified = user["Primary Verified"]
                secondary_verified = "TRUE"
                primary_subscribed = user["Primary Subscribed"]
                secondary_subscribed = "TRUE"

            info_fields = {}
            for row in edit_form.query.all():
                if row.field_type == "Checkbox":
                    vals = []
                    for val in user[row.label].split("\n"):
                        vals.append(val)
                    info_fields[row.label] = " ".join(vals)
                else:
                    info_fields[row.label] = user[row.label]

            event_fields = {}
            if event_obj is not None:
                if event_user is not None:
                    event_fields["Will you attend on Zoom or In-Person?"] = event_user["Will you attend on Zoom or In-Person?"]
                    event_fields["Ticket Type"] = event_user["Ticket Type"]

                    for question in event_obj.questions.split("\n"):
                        if event_wks_columns[question] > len(event_user):
                            event_fields[question] = ""
                        else:
                            event_fields[question] = event_user[question]

            subject = "I2G Membership Completed"
            html = render_template("info_receipt_email.html",
                                   event_url=event_url,
                                   update_url=update_url,
                                   first=user["First Name"], 
                                   last=user["Last Name"],
                                   primary_verified=primary_verified,
                                   secondary_verified=secondary_verified,
                                   primary_subscribed=primary_subscribed,
                                   secondary_subscribed=secondary_subscribed,
                                   info_fields=info_fields, 
                                   event_fields=event_fields, 
                                   event_name=event_obj.name if event_obj is not None else None)
            send_email(email, subject, html)
            
            return render_template("thanks_confirming.html", 
                                   event_url=event_url,
                                   update_url=update_url,
                                   first=user["First Name"],
                                   last=user["Last Name"],
                                   primary_verified=primary_verified,
                                   secondary_verified=secondary_verified,
                                   primary_subscribed=primary_subscribed,
                                   secondary_subscribed=secondary_subscribed,
                                   info_fields=info_fields,
                                   event_name=event_obj.name if event_obj is not None else None,
                                   event_fields=event_fields
                                )


@registration_blueprint.route("/resend-page/<token>")
def resend_page(token):
    return render_template("resend.html", token=token, _external=True)


@registration_blueprint.route("/resend/<token>")
def resend(token):
    email = confirm_token(token, None)

    wks_records = get_wks_records(wks)

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

    new_token = generate_token(email)
    url = url_for("registration.confirm", token=new_token, _external=True)
    html = render_template(
        "verify_email.html",
        first=user["First Name"],
        last=user["Last Name"],
        confirm_url=url,
    )

    thread = Thread(target=send_email, args=[email, app.config["VERIF_SUBJECT"], html])
    thread.start()

    return redirect(url_for("registration.resend_page", token=token, _external=True))


@registration_blueprint.route("/info-form/<token>", methods=["GET", "POST"])
def info(token):
    email = confirm_token(token, None)

    cells = []

    time.sleep(1)
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

    class InformationForm(FlaskForm):
        submit = SubmitField('Submit')

    person = {}

    for row in edit_form.query.all():
        setattr(InformationForm, row.label, get_field(row))

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

        setattr(InformationForm, "register_event", BooleanField(register_event_label, default=True))
        setattr(
            InformationForm, "event_zoom_or_not",
            RadioField("Will you attend on Zoom or In-Person?",
                       choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
                       validators=[Optional()]))
        setattr(
            InformationForm, "event_tickets",
            RadioField("Ticket Type",
                       choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                       validators=[Optional()]))

        for question in event_obj.questions.split("\n"):
            setattr(InformationForm, "event_" + question, StringField(question))

        if event_user is not None:
            person["register_event"] = True
            person["event_zoom_or_not"] = event_user["Will you attend on Zoom or In-Person?"]
            person["event_tickets"] = event_user["Ticket Type"]

            for question in event_obj.questions.split("\n"):
                if event_wks_columns[question] > len(event_user):
                    person["event_" + question] = ""
                else:
                    person["event_" + question] = event_user[question]

    form = InformationForm(data=person)

    if request.method == "POST" and form.validate_on_submit():
        wks_records = get_wks_records(wks)
        wks_columns = get_wks_columns(wks)

        if event_obj is not None:
            event_wks_records = get_wks_records(event_wks)
            event_wks_columns = get_wks_columns(event_wks)

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
        def update_sheet():
            cell_find = [row for row in wks_records if row["Primary Email"] == email]
            if not cell_find:
                cell_find = [row for row in wks_records if row["Secondary Email"] == email]

            row_find = cell_find[0]["Row"]

            for row in edit_form.query.all():
                if row.field_type == "Checkbox":
                    vals = []
                    choices = checkbox_get_choices(row.options)
                    for key in request.form.getlist(row.label):
                        vals.append(choices[int(key)][1])
                    cells.append(Cell(row_find, wks_columns[row.label], "\n".join(vals)))
                else:
                    cells.append(Cell(row_find, wks_columns[row.label], request.form[row.label]))

            cells.append(Cell(row_find, wks_columns["Info Completed"], "TRUE"))

            if event_obj is not None:
                if form.register_event.data:
                    if event_user is not None:
                        event_cells.append(
                            Cell(event_user["Row"], event_wks_columns["Last Updated"],
                                 str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))))
                        event_cells.append(
                            Cell(event_user["Row"], event_wks_columns["Will you attend on Zoom or In-Person?"], form.event_zoom_or_not.data))
                        event_cells.append(Cell(event_user["Row"], event_wks_columns["Ticket Type"], form.event_tickets.data))

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

            subject = "I2G Membership Completed"
            html = render_template("info_receipt_email.html", 
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
                                   
            send_email(email, subject, html)

        thread = Thread(target=update_sheet)
        thread.start()

        return render_template("receipt.html",
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

    else:
        return render_template("info_form.html", form=form, token=token, user=user)


@registration_blueprint.route("/full-registration/<token>", methods=["GET", "POST"])
def complete_registration(token):
    email = confirm_token(token, None)

    if not email:
        return render_template("error5.html")

    email = email.lower()

    cells = []

    global can_register
    can_register = True

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
        

    async def query_prim_col():
        return [row for row in wks_records if row["Primary Email"] == email]

    async def query_sec_col():
        return [row for row in wks_records if row["Secondary Email"] == email]

    async def main():
        return await asyncio.gather(query_prim_col(), query_sec_col())

    user = asyncio.run(main())
    user = user[0][0] if user[0] else user[1][0] if user[1] else None

    if user is not None:
        return render_template("error1.html")


    class CompleteRegistrationForm(FlaskForm):
        first_name = StringField("First Name", validators=[InputRequired()])
        last_name = StringField("Last Name", validators=[InputRequired()])
        primary_email = StringField('Primary Email Address', [InputRequired(' '), Email()])
        confirm_primary = StringField(
            'Confirm Primary Email',
            [InputRequired(' '), EqualTo('primary_email', message='Must match primary email')])
        secondary_email = StringField(
            'Secondary Email Address',
            [InputRequired(' '),
             Email(), NotEqualTo('primary_email', message='Can not be the same email')])
        confirm_secondary = StringField(
            'Confirm Secondary Email',
            [InputRequired(' '), EqualTo('secondary_email', message='Must match secondary email')])
        submit = SubmitField('Submit')

    for row in edit_form.query.all():
        setattr(CompleteRegistrationForm, row.label, get_field(row))

    if event_obj is not None:
        setattr(CompleteRegistrationForm, "register_event", BooleanField("Also register for " + event_obj.name + "?", default=True))
        setattr(
            CompleteRegistrationForm, "event_zoom_or_not",
            RadioField("Will you attend on Zoom or In-Person?",
                       choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
                       validators=[Optional()]))
        setattr(
            CompleteRegistrationForm, "event_tickets",
            RadioField("Ticket Type",
                       choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                       validators=[Optional()]))

        for question in event_obj.questions.split("\n"):
            setattr(CompleteRegistrationForm, "event_" + question, StringField(question))

    person = {"primary_email": email, "confirm_primary": email}

    form = CompleteRegistrationForm(data=person)
    form.primary_email.render_kw = {"readonly": True}
    form.confirm_primary.render_kw = {"readonly": True}

    if request.method == "POST" and form.validate_on_submit():
        def log_registration():
            order = int(logs.col_values(1)[-1]) + 1 if logs.col_values(1)[-1].isdigit() else 1
            row = [
                order, "/full-registration/<token>", str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")), "First Name: " + form.first_name.data,
                "Last Name: " + form.last_name.data, "Primary Email: " + form.primary_email.data, "Secondary Email: " + form.secondary_email.data, 
                "Register Event: " + str(form.register_event.data) if event_obj is not None else "No Event"
            ]
            logs.append_row(row)

        Thread(target=log_registration).start()

        wks_records = get_wks_records(wks)
        wks_columns = get_wks_columns(wks)

        if event_obj is not None:
            event_wks_records = get_wks_records(event_wks)
            event_wks_columns = get_wks_columns(event_wks)

        prim_email = request.form["primary_email"].lower()
        sec_email = request.form["secondary_email"].lower()

        async def search_sec_in_prim_col():
            user_sec1 = [row for row in wks_records if row["Primary Email"] == sec_email]
            if user_sec1:
                user_sec1 = user_sec1[0]
                row_sec1 = user_sec1["Row"]
            else:
                return

            if (user_sec1 is not None and user_sec1["Primary Expired"] == "TRUE"):
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
                    thread = Thread(target=send_email,
                                    args=(user_sec1["Secondary Email"], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_sec1 is not None and user_sec1["Primary Expired"] == "FALSE"):
                global can_register
                can_register = False
                if user_sec1["Primary Verified"] == "TRUE":
                    token = generate_token(user_sec1["Primary Email"])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec1["First Name"],
                        last=user_sec1["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_sec1["Primary Email"], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()
                    

        async def search_sec_in_sec_col():
            user_sec2 = [row for row in wks_records if row["Secondary Email"] == sec_email]
            if user_sec2:
                user_sec2 = user_sec2[0]
                row_sec2 = user_sec2["Row"]
            else:
                return

            if (user_sec2 is not None and user_sec2["Secondary Expired"] == "TRUE"):
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
                    thread = Thread(target=send_email,
                                    args=(user_sec2["Primary Email"], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_sec2 is not None and user_sec2["Secondary Expired"] == "FALSE"):
                global can_register
                can_register = False
                if user_sec2["Secondary Verified"] == "TRUE":
                    token = generate_token(user_sec2["Secondary Email"])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec2["First Name"],
                        last=user_sec2["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_sec2["Secondary Email"], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()

        async def update_sheet():
            if len(cells) > 0:
                wks.update_cells(cells)

            if len(event_cells) > 0:
                event_wks.update_cells(event_cells)

        async def main():
            await asyncio.gather(search_sec_in_prim_col(), search_sec_in_sec_col(), update_sheet())

        asyncio.run(main())

        if not can_register:
            return render_template("error1.html")
        else:
            info_fields = {}
            for row in edit_form.query.all():
                if row.field_type == "Checkbox":
                    vals = []
                    choices = checkbox_get_choices(row.options)
                    for key in request.form.getlist(row.label):
                        vals.append(choices[int(key)][1])
                    info_fields[row.label] = " ".join(vals)
                else:
                    info_fields[row.label] = request.form[row.label]

            event_fields = {}
            if event_obj is not None:
                if form.register_event.data:
                    event_fields["Will you attend on Zoom or In-Person?"] = form.event_zoom_or_not.data
                    event_fields["Ticket Type"] = form.event_tickets.data

                    for question in event_obj.questions.split("\n"):
                        event_fields[question] = form["event_" + question].data

            @copy_current_request_context
            def can_register():
                user = ["" for i in range(len(wks_columns))]

                user[wks_columns["Order"] - 1] = int(wks.col_values(wks_columns["Order"])[-1]) + 1 if wks.col_values(
                    wks_columns["Order"])[-1].isdigit() else 1
                user[wks_columns["First Name"] - 1] = form.first_name.data
                user[wks_columns["Last Name"] - 1] = form.last_name.data
                user[wks_columns["When Started"] - 1] = str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))
                user[wks_columns["Last Updated"] - 1] = str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))
                user[wks_columns["Primary Email"] - 1] = prim_email
                user[wks_columns["Primary Verified"] - 1] = "TRUE"
                user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
                user[wks_columns["Primary Expired"] - 1] = "FALSE"
                user[wks_columns["Primary Bounced"] - 1] = ""
                user[wks_columns["Secondary Email"] - 1] = sec_email
                user[wks_columns["Secondary Verified"] - 1] = "FALSE"
                user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
                user[wks_columns["Secondary Expired"] - 1] = "FALSE"
                user[wks_columns["Secondary Bounced"] - 1] = ""
                user[wks_columns["Info Completed"] - 1] = "TRUE"

                for row in edit_form.query.all():
                    if row.field_type == "Checkbox":
                        vals = []
                        choices = checkbox_get_choices(row.options)
                        for key in request.form.getlist(row.label):
                            vals.append(choices[int(key)][1])
                        user[wks_columns[row.label] - 1] = "\n".join(vals)
                    else:
                        user[wks_columns[row.label] - 1] = request.form[row.label]

                wks.append_row(user)

                s_token = generate_token(sec_email)
                s_confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                s_html = render_template(
                    "verify_email.html",
                    first=form.first_name.data,
                    last=form.last_name.data,
                    confirm_url=s_confirm_url,
                )

                send_email(sec_email, app.config["VERIF_SUBJECT"], s_html)

                def sec_expiry_timer():
                    time.sleep(app.config["EXPIRY_TIMER"])
                    wks_records = get_wks_records(wks)
                    wks_columns = get_wks_columns(wks)
                    row = [row for row in wks_records if row["Secondary Email"] == sec_email]
                    if row:
                        row = row[0]
                        if row["Secondary Verified"] == "FALSE":
                            wks.update_cell(row["Row"], wks_columns["Secondary Expired"], "TRUE")

                thread = Thread(target=sec_expiry_timer)
                thread.start()

                if event_obj is not None:
                    if form.register_event.data:
                        event_row = ["" for i in range(len(event_wks_columns))]

                        event_row[event_wks_columns["Order"] - 1] = int(
                            event_wks.col_values(event_wks_columns["Order"])[-1]) + 1 if event_wks.col_values(
                                event_wks_columns["Order"])[-1].isdigit() else 1
                        event_row[event_wks_columns["First Name"] - 1] = form.first_name.data
                        event_row[event_wks_columns["Last Name"] - 1] = form.last_name.data
                        event_row[event_wks_columns["When Started"] - 1] = str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))
                        event_row[event_wks_columns["Last Updated"] - 1] = str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))
                        event_row[event_wks_columns["Membership Primary"] - 1] = prim_email
                        event_row[event_wks_columns["Membership Secondary"] - 1] = sec_email
                        event_row[event_wks_columns["Ticket Type"] - 1] = form.event_tickets.data
                        event_row[event_wks_columns["Will you attend on Zoom or In-Person?"] - 1] = form.event_zoom_or_not.data

                        for question in event_obj.questions.split("\n"):
                            form_key = "event_" + question
                            event_row[event_wks_columns[question] - 1] = form[form_key].data

                        event_wks.append_row(event_row)


                subject = "I2G Membership Completed"
                html = render_template("info_receipt_email.html",
                                    event_url=event_url, 
                                    update_url=update_url,
                                    first=user[wks_columns["First Name"] - 1],
                                    last=user[wks_columns["Last Name"] - 1],
                                    primary_email=user[wks_columns["Primary Email"] - 1],
                                    primary_verified=user[wks_columns["Primary Verified"] - 1],
                                    primary_subscribed=user[wks_columns["Primary Subscribed"] - 1],
                                    secondary_email=user[wks_columns["Secondary Email"] - 1],
                                    secondary_verified=user[wks_columns["Secondary Verified"] - 1],
                                    secondary_subscribed=user[wks_columns["Secondary Subscribed"] - 1],
                                    info_fields=info_fields,
                                    event_name=event_obj.name if event_obj is not None else None,
                                    event_fields=event_fields)
                                    
                send_email(email, subject, html)

            thread = Thread(target=can_register)
            thread.start()

            return render_template("receipt.html",
                                    event_url=event_url,
                                    update_url=update_url,
                                    first=form.first_name.data,
                                    last=form.last_name.data,
                                    primary_email=form.primary_email.data,
                                    primary_verified="TRUE",
                                    primary_subscribed="TRUE",
                                    secondary_email=form.secondary_email.data,
                                    secondary_verified="FALSE",
                                    secondary_subscribed="FALSE",
                                    info_fields=info_fields,
                                    event_name=event_obj.name if event_obj is not None else None,
                                    event_fields=event_fields)

    else:
        return render_template("complete_registration.html", form=form, token=token)