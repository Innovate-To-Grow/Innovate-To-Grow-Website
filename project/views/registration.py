import asyncio, time
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, render_template, url_for, request, redirect, copy_current_request_context
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField
from wtforms.validators import EqualTo, Email, InputRequired, Optional
from project import app, wks, sh
from project.models import edit_form, event
from project.utils.email import send_email
from project.utils.field import get_field, checkbox_get_choices
from project.utils.token import generate_token, confirm_token, confirm_token_no_expiry
from project.utils.index_helper import wks_indices, arr_indices
from project.forms.registration_forms import NotEqualTo, RegistrationForm

registration_blueprint = Blueprint("registration",
                                   __name__,
                                   template_folder="../templates/membership/registration",
                                   url_prefix=app.config["URL_PREFIX"])


@registration_blueprint.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm()

    cells = []

    global can_register
    can_register = True

    wks_idx = wks_indices(wks)
    arr_idx = arr_indices(wks)

    event_cells = []
    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is not None:
        event_wks = sh.worksheet(event_obj.name)
        event_wks_idx = wks_indices(event_wks)

    if request.method == "POST" and form.validate_on_submit():

        def log_registration():
            worksheets = []
            for worksheet in sh.worksheets():
                worksheets.append(worksheet.title)

            if "Registration Logs" not in worksheets:
                sh.add_worksheet("Registration Logs", 1, 6)
                sh.worksheet("Registration Logs").append_row(
                    ["Order", "First Name", "Last Name", "Primary Email", "Secondary Email", "DateTime"])

            order = int(sh.worksheet("Registration Logs").col_values(1)[-1]) + 1 if sh.worksheet(
                "Registration Logs").col_values(1)[-1].isdigit() else 1

            row = [
                order, form.first_name.data, form.last_name.data, form.primary_email.data, form.secondary_email.data,
                str(datetime.now().replace(second=0, microsecond=0))
            ]
            sh.worksheet("Registration Logs").append_row(row)

        Thread(target=log_registration).start()

        prim_email = request.form["primary_email"].lower()
        sec_email = request.form["secondary_email"].lower()

        async def search_prim_in_prim_col():
            user_prim1 = wks.find(prim_email, in_column=wks_idx["Primary Email"])
            if user_prim1 is not None:
                row_prim1 = user_prim1.row
                user_prim1 = wks.row_values(row_prim1)

            if (user_prim1 is not None and user_prim1[arr_idx["Primary Expired"]] == "TRUE"):
                cells.append(Cell(row_prim1, wks_idx["Primary Email"], ""))

                if event_obj is not None:
                    event_user = event_wks.find(prim_email, in_column=event_wks_idx["Membership Primary"])
                    if event_user is not None:
                        event_cells.append(Cell(event_user.row, event_wks_idx["Membership Primary"], ""))

                if user_prim1[arr_idx["Secondary Email"]] != "" and user_prim1[arr_idx["Secondary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_prim1[arr_idx["First Name"]],
                                           last=user_prim1[arr_idx["Last Name"]],
                                           email=user_prim1[arr_idx["Primary Email"]])
                    thread = Thread(target=send_email,
                                    args=(user_prim1[arr_idx["Secondary Email"]], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_prim1 is not None and user_prim1[arr_idx["Primary Expired"]] == "FALSE"):
                global can_register
                can_register = False
                if user_prim1[arr_idx["Primary Verified"]] == "TRUE":
                    token = generate_token(user_prim1[arr_idx["Primary Email"]])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_prim1[arr_idx["First Name"]],
                        last=user_prim1[arr_idx["Last Name"]],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_prim1[arr_idx["Primary Email"]], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()

        async def search_prim_in_sec_col():
            user_prim2 = wks.find(prim_email, in_column=wks_idx["Secondary Email"])
            if user_prim2 is not None:
                row_prim2 = user_prim2.row
                user_prim2 = wks.row_values(row_prim2)

            if (user_prim2 is not None and user_prim2[arr_idx["Secondary Expired"]] == "TRUE"):
                cells.append(Cell(row_prim2, wks_idx["Secondary Email"], ""))

                if event_obj is not None:
                    event_user = event_wks.find(prim_email, in_column=event_wks_idx["Membership Secondary"])
                    if event_user is not None:
                        event_cells.append(Cell(event_user.row, event_wks_idx["Membership Secondary"], ""))

                if user_prim2[arr_idx["Primary Email"]] != "" and user_prim2[arr_idx["Primary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_prim2[arr_idx["First Name"]],
                                           last=user_prim2[arr_idx["Last Name"]],
                                           email=user_prim2[arr_idx["Secondary Email"]])
                    thread = Thread(target=send_email,
                                    args=(user_prim2[arr_idx["Primary Email"]], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_prim2 is not None and user_prim2[arr_idx["Secondary Expired"]] == "FALSE"):
                global can_register
                can_register = False
                if user_prim2[arr_idx["Secondary Verified"]] == "TRUE":
                    token = generate_token(user_prim2[arr_idx["Secondary Email"]])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_prim2[arr_idx["First Name"]],
                        last=user_prim2[arr_idx["Last Name"]],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_prim2[arr_idx["Secondary Email"]], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()

        async def search_sec_in_prim_col():
            user_sec1 = wks.find(sec_email, in_column=wks_idx["Primary Email"])
            if user_sec1 is not None:
                row_sec1 = user_sec1.row
                user_sec1 = wks.row_values(row_sec1)

            if (user_sec1 is not None and user_sec1[arr_idx["Primary Expired"]] == "TRUE"):
                cells.append(Cell(row_sec1, wks_idx["Primary Email"], ""))

                if event_obj is not None:
                    event_user = event_wks.find(sec_email, in_column=event_wks_idx["Membership Primary"])
                    if event_user is not None:
                        event_cells.append(Cell(event_user.row, event_wks_idx["Membership Primary"], ""))

                if user_sec1[arr_idx["Secondary Email"]] != "" and user_sec1[arr_idx["Secondary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_sec1[arr_idx["First Name"]],
                                           last=user_sec1[arr_idx["Last Name"]],
                                           email=user_sec1[arr_idx["Primary Email"]])
                    thread = Thread(target=send_email,
                                    args=(user_sec1[arr_idx["Secondary Email"]], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_sec1 is not None and user_sec1[arr_idx["Primary Expired"]] == "FALSE"):
                global can_register
                can_register = False
                if user_sec1[arr_idx["Primary Verified"]] == "TRUE":
                    token = generate_token(user_sec1[arr_idx["Primary Email"]])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec1[arr_idx["First Name"]],
                        last=user_sec1[arr_idx["Last Name"]],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_sec1[arr_idx["Primary Email"]], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()

        async def search_sec_in_sec_col():
            user_sec2 = wks.find(sec_email, in_column=wks_idx["Secondary Email"])
            if user_sec2 is not None:
                row_sec2 = user_sec2.row
                user_sec2 = wks.row_values(row_sec2)

            if (user_sec2 is not None and user_sec2[arr_idx["Secondary Expired"]] == "TRUE"):
                cells.append(Cell(row_sec2, wks_idx["Secondary Email"], ""))

                if event_obj is not None:
                    event_user = event_wks.find(sec_email, in_column=event_wks_idx["Membership Secondary"])
                    if event_user is not None:
                        event_cells.append(Cell(event_user.row, event_wks_idx["Membership Secondary"], ""))

                if user_sec2[arr_idx["Primary Email"]] != "" and user_sec2[arr_idx["Primary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_sec2[arr_idx["First Name"]],
                                           last=user_sec2[arr_idx["Last Name"]],
                                           email=user_sec2[arr_idx["Secondary Email"]])
                    thread = Thread(target=send_email,
                                    args=(user_sec2[arr_idx["Primary Email"]], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_sec2 is not None and user_sec2[arr_idx["Secondary Expired"]] == "FALSE"):
                global can_register
                can_register = False
                if user_sec2[arr_idx["Secondary Verified"]] == "TRUE":
                    token = generate_token(user_sec2[arr_idx["Secondary Email"]])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec2[arr_idx["First Name"]],
                        last=user_sec2[arr_idx["Last Name"]],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_sec2[arr_idx["Secondary Email"]], app.config["UPDATE_SUBJECT"],
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
                user = ["" for i in range(len(wks_idx))]

                user[arr_idx["Order"]] = int(wks.col_values(wks_idx["Order"])[-1]) + 1 if wks.col_values(
                    wks_idx["Order"])[-1].isdigit() else 1
                user[arr_idx["First Name"]] = form.first_name.data
                user[arr_idx["Last Name"]] = form.last_name.data
                user[arr_idx["When Started"]] = str(datetime.now().replace(second=0, microsecond=0))
                user[arr_idx["Last Updated"]] = str(datetime.now().replace(second=0, microsecond=0))
                user[arr_idx["Primary Email"]] = prim_email
                user[arr_idx["Primary Verified"]] = "FALSE"
                user[arr_idx["Primary Subscribed"]] = "FALSE"
                user[arr_idx["Primary Expired"]] = "FALSE"
                user[arr_idx["Primary Bounced"]] = ""
                user[arr_idx["Secondary Email"]] = sec_email
                user[arr_idx["Secondary Verified"]] = "FALSE"
                user[arr_idx["Secondary Subscribed"]] = "FALSE"
                user[arr_idx["Secondary Expired"]] = "FALSE"
                user[arr_idx["Secondary Bounced"]] = ""
                user[arr_idx["Info Completed"]] = "FALSE"

                wks.append_row(user)

                p_token = generate_token(prim_email)
                p_confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                p_html = render_template(
                    "verify_email.html",
                    first=user[arr_idx["First Name"]],
                    last=user[arr_idx["Last Name"]],
                    confirm_url=p_confirm_url,
                )

                s_token = generate_token(sec_email)
                s_confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                s_html = render_template(
                    "verify_email.html",
                    first=user[arr_idx["First Name"]],
                    last=user[arr_idx["Last Name"]],
                    confirm_url=s_confirm_url,
                )

                send_email(prim_email, app.config["VERIF_SUBJECT"], p_html)
                send_email(sec_email, app.config["VERIF_SUBJECT"], s_html)

                def expiry_timer():
                    time.sleep(app.config["VERIF_EXPIRATION"])
                    row = wks.find(prim_email, in_column=wks_idx["Primary Email"]).row
                    user = wks.row_values(row)
                    if user[arr_idx["Primary Verified"]] == "FALSE":
                        wks.update_cell(row, wks_idx["Primary Expired"], "TRUE")
                    if user[arr_idx["Secondary Verified"]] == "FALSE":
                        wks.update_cell(row, wks_idx["Secondary Expired"], "TRUE")

                thread = Thread(target=expiry_timer)
                thread.start()

            thread = Thread(target=can_register)
            thread.start()

            return render_template("instructions_sent.html")

    else:
        return render_template("register_form.html", form=form)


@registration_blueprint.route("/con<token>")
def confirm(token):
    user = None
    email = confirm_token(token)

    wks_idx = wks_indices(wks)
    arr_idx = arr_indices(wks)

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
            return render_template("error2.html")
        else:
            verif_col = arr_idx["Primary Verified"] if user.col == wks_idx["Primary Email"] else arr_idx[
                "Secondary Verified"]
            user = wks.row_values(user.row)

    if user is None:
        return redirect(url_for("registration.resend_page", token=token, _external=True))

    elif user[verif_col] == "TRUE" and user[arr_idx["Info Completed"]] == "TRUE":
        return render_template("already_confirmed.html")

    else:

        def update_sheet():
            cell_find = wks.find(email, in_column=wks_idx["Primary Email"])
            if cell_find is None:
                cell_find = wks.find(email, in_column=wks_idx["Secondary Email"])
                verified = wks_idx["Secondary Verified"]
                subscribed = wks_idx["Secondary Subscribed"]
                expired = wks_idx["Secondary Expired"]
            else:
                verified = wks_idx["Primary Verified"]
                subscribed = wks_idx["Primary Subscribed"]
                expired = wks_idx["Primary Expired"]

            row_find = cell_find.row

            cells = []
            cells.append(Cell(row_find, verified, "TRUE"))
            cells.append(Cell(row_find, subscribed, "TRUE"))
            cells.append(Cell(row_find, expired, "FALSE"))

            if len(cells) > 0:
                wks.update_cells(cells)

        thread = Thread(target=update_sheet)
        thread.start()

        if user[arr_idx["Info Completed"]] == "FALSE":
            return redirect(url_for("registration.info", token=token, _external=True))
        else:
            return render_template("thanks_confirming.html")


@registration_blueprint.route("/res<token>p")
def resend_page(token):
    return render_template("resend.html", token=token, _external=True)


@registration_blueprint.route("/res<token>")
def resend(token):
    email = confirm_token_no_expiry(token)

    wks_idx = wks_indices(wks)
    arr_idx = arr_indices(wks)

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
            return render_template("error2.html")
        else:
            user = wks.row_values(user.row)
    else:
        return render_template("error2.html")

    new_token = generate_token(email)
    url = url_for("registration.confirm", token=new_token, _external=True)
    html = render_template(
        "verify_email.html",
        first=user[arr_idx["First Name"]],
        last=user[arr_idx["Last Name"]],
        confirm_url=url,
    )

    thread = Thread(target=send_email, args=[email, app.config["VERIF_SUBJECT"], html])
    thread.start()

    return redirect(url_for("registration.resend_page", token=token, _external=True))


@registration_blueprint.route("/info/<token>", methods=["GET", "POST"])
def info(token):
    email = confirm_token_no_expiry(token)

    cells = []

    wks_idx = wks_indices(wks)
    arr_idx = arr_indices(wks)

    event_cells = []
    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is not None:
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
            return render_template("error2.html")
        else:
            user = wks.row_values(user.row)
    else:
        return render_template("error2.html")

    class InformationForm(FlaskForm):
        submit = SubmitField('Submit')

    person = {}

    for row in edit_form.query.all():
        setattr(InformationForm, row.label, get_field(row))

    if event_obj is not None:
        setattr(InformationForm, "register_event", BooleanField("Also register for " + event_obj.name + "?"))
        setattr(
            InformationForm, "event_zoom_or_not",
            RadioField("Zoom or In-Person",
                       choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
                       validators=[Optional()]))
        setattr(
            InformationForm, "event_tickets",
            RadioField("Ticket Type",
                       choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                       validators=[Optional()]))

        for question in event_obj.questions.split("\n"):
            setattr(InformationForm, "event_" + question, StringField(question))

        async def query_event_prim_col():
            return event_wks.find(email, in_column=event_wks_idx["Membership Primary"])

        async def query_event_sec_col():
            return event_wks.find(email, in_column=event_wks_idx["Membership Secondary"])

        async def main():
            return await asyncio.gather(query_event_prim_col(), query_event_sec_col())

        event_user = asyncio.run(main())
        event_user = event_user[0] if event_user[0] is not None else event_user[1] if event_user[1] is not None else None

        if event_user is not None:
            temp_event_user = event_wks.row_values(event_user.row)
            person["register_event"] = True
            person["event_zoom_or_not"] = temp_event_user[event_arr_idx["Zoom or In-Person?"]]
            person["event_tickets"] = temp_event_user[event_arr_idx["Ticket Type"]]

            for question in event_obj.questions.split("\n"):
                if event_wks_idx[question] > len(temp_event_user):
                    person["event_" + question] = ""
                else:
                    person["event_" + question] = temp_event_user[event_arr_idx[question]]

    form = InformationForm(data=person)

    if request.method == "POST" and form.validate_on_submit():

        @copy_current_request_context
        def update_sheet():
            cell_find = wks.find(email, in_column=wks_idx["Primary Email"])
            if cell_find is None:
                cell_find = wks.find(email, in_column=wks_idx["Secondary Email"])

            row_find = cell_find.row

            for row in edit_form.query.all():
                if row.field_type == "Checkbox":
                    vals = []
                    choices = checkbox_get_choices(row.options)
                    for key in request.form.getlist(row.label):
                        vals.append(choices[int(key)][1])
                    cells.append(Cell(row_find, wks_idx[row.label], "\n".join(vals)))
                else:
                    cells.append(Cell(row_find, wks_idx[row.label], request.form[row.label]))

            cells.append(Cell(row_find, wks_idx["Info Completed"], "TRUE"))

            if event_obj is not None:
                if form.register_event.data:
                    if event_user is not None:
                        event_cells.append(
                            Cell(event_user.row, event_wks_idx["Last Updated"],
                                 str(datetime.now().replace(second=0, microsecond=0))))
                        event_cells.append(
                            Cell(event_user.row, event_wks_idx["Zoom or In-Person?"], form.event_zoom_or_not.data))
                        event_cells.append(Cell(event_user.row, event_wks_idx["Ticket Type"], form.event_tickets.data))

                        for question in event_obj.questions.split("\n"):
                            event_cells.append(
                                Cell(event_user.row, event_wks_idx[question], form["event_" + question].data))

                    else:
                        row = ["" for i in range(len(event_wks.row_values(1)))]

                        row[event_arr_idx["Order"]] = int(
                            event_wks.col_values(1)[-1]) + 1 if event_wks.col_values(1)[-1].isdigit() else 1
                        row[event_arr_idx["First Name"]] = user[arr_idx["First Name"]]
                        row[event_arr_idx["Last Name"]] = user[arr_idx["Last Name"]]
                        row[event_arr_idx["When Started"]] = str(datetime.now().replace(second=0, microsecond=0))
                        row[event_arr_idx["Last Updated"]] = str(datetime.now().replace(second=0, microsecond=0))
                        row[event_arr_idx["Membership Primary"]] = user[arr_idx["Primary Email"]]
                        row[event_arr_idx["Membership Secondary"]] = user[arr_idx["Secondary Email"]]
                        row[event_arr_idx["Ticket Type"]] = form.event_tickets.data
                        row[event_arr_idx["Zoom or In-Person?"]] = form.event_zoom_or_not.data

                        for question in event_obj.questions.split("\n"):
                            row[event_arr_idx[question]] = form["event_" + question].data

                        event_wks.append_row(row)

            if len(cells) > 0:
                wks.update_cells(cells)

            if len(event_cells) > 0:
                event_wks.update_cells(event_cells)

        thread = Thread(target=update_sheet)
        thread.start()

        return render_template("thanks_registering.html")

    else:
        return render_template("info_form.html", form=form, token=token)


@registration_blueprint.route("/complete-registration/<token>", methods=["GET", "POST"])
def complete_registration(token):
    email = confirm_token_no_expiry(token)

    if not email:
        return render_template("error5.html")

    email = email.lower()

    cells = []

    global can_register
    can_register = True

    wks_idx = wks_indices(wks)
    arr_idx = arr_indices(wks)

    event_cells = []
    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    if event_obj is not None:
        event_wks = sh.worksheet(event_obj.name)
        event_wks_idx = wks_indices(event_wks)
        event_arr_idx = arr_indices(event_wks)

    async def query_prim_col():
        return wks.find(email, in_column=wks_idx["Primary Email"])

    async def query_sec_col():
        return wks.find(email, in_column=wks_idx["Secondary Email"])

    async def main():
        return await asyncio.gather(query_prim_col(), query_sec_col())

    user = asyncio.run(main())
    user = user[0] if user[0] is not None else user[1] if user[1] is not None else None

    if user is not None:
        return render_template("error1.html")

    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    class CompleteRegistrationForm(FlaskForm):
        first_name = StringField("First Name", validators=[InputRequired()])
        last_name = StringField("Last Name", validators=[InputRequired()])
        primary_email = StringField('Primary Email Address', [InputRequired(' '), Email()])
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
        setattr(CompleteRegistrationForm, "register_event", BooleanField("Also register for " + event_obj.name + "?"))
        setattr(
            CompleteRegistrationForm, "event_zoom_or_not",
            RadioField("Zoom or In-Person",
                       choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
                       validators=[Optional()]))
        setattr(
            CompleteRegistrationForm, "event_tickets",
            RadioField("Ticket Type",
                       choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                       validators=[Optional()]))

        for question in event_obj.questions.split("\n"):
            setattr(CompleteRegistrationForm, "event_" + question, StringField(question))

    person = {"primary_email": email}

    form = CompleteRegistrationForm(data=person)
    form.primary_email.render_kw = {"readonly": True}

    if request.method == "POST" and form.validate_on_submit():
        prim_email = request.form["primary_email"].lower()
        sec_email = request.form["secondary_email"].lower()

        async def search_sec_in_prim_col():
            user_sec1 = wks.find(sec_email, in_column=wks_idx["Primary Email"])
            if user_sec1 is not None:
                row_sec1 = user_sec1.row
                user_sec1 = wks.row_values(row_sec1)

            if (user_sec1 is not None and user_sec1[arr_idx["Primary Expired"]] == "TRUE"):
                cells.append(Cell(row_sec1, wks_idx["Primary Email"], ""))

                if event_obj is not None:
                    event_user = event_wks.find(sec_email, in_column=event_wks_idx["Membership Primary"])
                    if event_user is not None:
                        event_cells.append(Cell(event_user.row, event_wks_idx["Membership Primary"], ""))

                if user_sec1[arr_idx["Secondary Email"]] != "" and user_sec1[arr_idx["Secondary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_sec1[arr_idx["First Name"]],
                                           last=user_sec1[arr_idx["Last Name"]],
                                           email=user_sec1[arr_idx["Primary Email"]])
                    thread = Thread(target=send_email,
                                    args=(user_sec1[arr_idx["Secondary Email"]], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_sec1 is not None and user_sec1[arr_idx["Primary Expired"]] == "FALSE"):
                global can_register
                can_register = False
                if user_sec1[arr_idx["Primary Verified"]] == "TRUE":
                    token = generate_token(user_sec1[arr_idx["Primary Email"]])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec1[arr_idx["First Name"]],
                        last=user_sec1[arr_idx["Last Name"]],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_sec1[arr_idx["Primary Email"]], app.config["UPDATE_SUBJECT"],
                                          update_html))
                    thread.start()

        async def search_sec_in_sec_col():
            user_sec2 = wks.find(sec_email, in_column=wks_idx["Secondary Email"])
            if user_sec2 is not None:
                row_sec2 = user_sec2.row
                user_sec2 = wks.row_values(row_sec2)

            if (user_sec2 is not None and user_sec2[arr_idx["Secondary Expired"]] == "TRUE"):
                cells.append(Cell(row_sec2, wks_idx["Secondary Email"], ""))

                if event_obj is not None:
                    event_user = event_wks.find(sec_email, in_column=event_wks_idx["Membership Secondary"])
                    if event_user is not None:
                        event_cells.append(Cell(event_user.row, event_wks_idx["Membership Secondary"], ""))

                if user_sec2[arr_idx["Primary Email"]] != "" and user_sec2[arr_idx["Primary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_sec2[arr_idx["First Name"]],
                                           last=user_sec2[arr_idx["Last Name"]],
                                           email=user_sec2[arr_idx["Secondary Email"]])
                    thread = Thread(target=send_email,
                                    args=(user_sec2[arr_idx["Primary Email"]], app.config["REMOVE_SUBJECT"], html))
                    thread.start()

            elif (user_sec2 is not None and user_sec2[arr_idx["Secondary Expired"]] == "FALSE"):
                global can_register
                can_register = False
                if user_sec2[arr_idx["Secondary Verified"]] == "TRUE":
                    token = generate_token(user_sec2[arr_idx["Secondary Email"]])
                    update_url = url_for("update.update_info", token=token, _external=True)
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec2[arr_idx["First Name"]],
                        last=user_sec2[arr_idx["Last Name"]],
                        update_url=update_url,
                    )
                    thread = Thread(target=send_email,
                                    args=(user_sec2[arr_idx["Secondary Email"]], app.config["UPDATE_SUBJECT"],
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

            @copy_current_request_context
            def can_register():
                user = ["" for i in range(len(wks_idx))]

                user[arr_idx["Order"]] = int(wks.col_values(wks_idx["Order"])[-1]) + 1 if wks.col_values(
                    wks_idx["Order"])[-1].isdigit() else 1
                user[arr_idx["First Name"]] = form.first_name.data
                user[arr_idx["Last Name"]] = form.last_name.data
                user[arr_idx["When Started"]] = str(datetime.now().replace(second=0, microsecond=0))
                user[arr_idx["Last Updated"]] = str(datetime.now().replace(second=0, microsecond=0))
                user[arr_idx["Primary Email"]] = prim_email
                user[arr_idx["Primary Verified"]] = "TRUE"
                user[arr_idx["Primary Subscribed"]] = "TRUE"
                user[arr_idx["Primary Expired"]] = "FALSE"
                user[arr_idx["Primary Bounced"]] = ""
                user[arr_idx["Secondary Email"]] = sec_email
                user[arr_idx["Secondary Verified"]] = "FALSE"
                user[arr_idx["Secondary Subscribed"]] = "FALSE"
                user[arr_idx["Secondary Expired"]] = "FALSE"
                user[arr_idx["Secondary Bounced"]] = ""
                user[arr_idx["Info Completed"]] = "TRUE"

                for row in edit_form.query.all():
                    if row.field_type == "Checkbox":
                        vals = []
                        choices = checkbox_get_choices(row.options)
                        for key in request.form.getlist(row.label):
                            vals.append(choices[int(key)][1])
                        user[arr_idx[row.label]] = "\n".join(vals)
                    else:
                        user[arr_idx[row.label]] = request.form[row.label]

                wks.append_row(user)

                s_token = generate_token(sec_email)
                s_confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                s_html = render_template(
                    "verify_email.html",
                    first=user[arr_idx["First Name"]],
                    last=user[arr_idx["Last Name"]],
                    confirm_url=s_confirm_url,
                )

                send_email(sec_email, app.config["VERIF_SUBJECT"], s_html)

                def sec_expiry_timer():
                    time.sleep(app.config["VERIF_EXPIRATION"])
                    row = wks.find(sec_email, in_column=wks_idx["Secondary Email"]).row
                    user = wks.row_values(row)
                    if user[arr_idx["Secondary Verified"]] == "FALSE":
                        wks.update_cell(row, wks_idx["Secondary Expired"], "TRUE")

                thread = Thread(target=sec_expiry_timer)
                thread.start()

                if event_obj is not None:
                    if form.register_event.data:
                        event_row = ["" for i in range(len(event_wks_idx))]

                        event_row[event_arr_idx["Order"]] = int(
                            event_wks.col_values(1)[-1]) + 1 if event_wks.col_values(1)[-1].isdigit() else 1
                        event_row[event_arr_idx["First Name"]] = form.first_name.data
                        event_row[event_arr_idx["Last Name"]] = form.last_name.data
                        event_row[event_arr_idx["When Started"]] = str(datetime.now().replace(second=0, microsecond=0))
                        event_row[event_arr_idx["Last Updated"]] = str(datetime.now().replace(second=0, microsecond=0))
                        event_row[event_arr_idx["Membership Primary"]] = prim_email
                        event_row[event_arr_idx["Membership Secondary"]] = sec_email
                        event_row[event_arr_idx["Ticket Type"]] = form.event_tickets.data
                        event_row[event_arr_idx["Zoom or In-Person?"]] = form.event_zoom_or_not.data

                        for question in event_obj.questions.split("\n"):
                            form_key = "event_" + question
                            event_row[event_arr_idx[question]] = form[form_key].data

                        event_wks.append_row(event_row)

            thread = Thread(target=can_register)
            thread.start()

            return render_template("instructions_sent.html")

    else:
        return render_template("complete_registration.html", form=form, token=token)