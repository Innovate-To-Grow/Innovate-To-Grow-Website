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
from project.utils.event_utils import make_sure, analyze_email_changes, calculate_verification_cell_updates, calculate_basic_user_updates
from project.utils.side_effect_helpers import (
    execute_cell_updates, send_verification_email, refresh_user_data,
    create_event_registration, update_subscription_status, update_completion_status,
    send_confirmation_email
)
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
        # setattr(
        #     UpdateForm, "event_zoom_or_not",
        #     RadioField("Will you attend on Zoom or In-Person?",
        #                choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
        #                validators=[Optional()]))
        setattr(
            UpdateForm, "event_tickets",
            RadioField("Ticket Type",
                       choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                       validators=[Optional()]))

        for question in event_obj.questions.split("\n"):
            setattr(UpdateForm, "event_" + question, StringField(question))

        if event_user is not None:
            person["register_event"] = True
            # person["event_zoom_or_not"] = event_user["Will you attend on Zoom or In-Person?"]
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

        prim_email = form.primary_email.data.lower()
        sec_email = form.secondary_email.data.lower()


        # Use the refactored validation function
        can_update, cells_to_update, emails_to_send = make_sure(
            can_update, wks_records, row_find, prim_email, sec_email
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
                if form.register_event.data:
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

                else:
                    if event_user is not None:
                        # event_fields["Will you attend on Zoom or In-Person?"] = event_user["Will you attend on Zoom or In-Person?"]
                        event_fields["Ticket Type"] = event_user["Ticket Type"]

                        for question in event_obj.questions.split("\n"):
                            if event_wks_columns[question] > len(event_user):
                                event_fields[question] = ""
                            else:
                                event_fields[question] = event_user[question]

            @copy_current_request_context
            def execute_user_update():
                """Refactored function using separated logic and side effects"""

                # PHASE 1: ANALYZE EMAIL CHANGES (Pure Logic)
                decision = analyze_email_changes(user, prim_email, sec_email)

                # PHASE 2: CALCULATE REQUIRED UPDATES (Pure Logic)
                # Get custom fields for form processing
                custom_fields = [{"label": row.label, "field_type": row.field_type}
                               for row in edit_form.query.all()]

                # Prepare form data for processing
                form_data = {
                    "first_name": form.first_name.data,
                    "last_name": form.last_name.data,
                    "primary_email": prim_email,
                    "secondary_email": sec_email,
                }

                # Add custom field data
                for row in edit_form.query.all():
                    field = form[row.label]
                    if row.field_type == "Checkbox":
                        vals = []
                        choices = checkbox_get_choices(row.options)
                        for key in field.data:
                            vals.append(choices[int(key)][1])
                        form_data[row.label] = vals
                    else:
                        form_data[row.label] = field.data

                # Calculate all required cell updates
                basic_updates = calculate_basic_user_updates(form_data, row_find, custom_fields)
                verification_updates = calculate_verification_cell_updates(user, decision, row_find)

                # PHASE 3: EXECUTE SIDE EFFECTS
                # 3.1: Execute database updates
                all_updates = basic_updates + verification_updates
                execute_cell_updates(all_updates, "membership")

                # 3.2: Send verification emails for new emails
                for email in decision.emails_needing_verification:
                    send_verification_email(email, user["First Name"], user["Last Name"])

                # 3.3: Handle event registration if user opted for it
                if event_obj is not None and form.register_event.data:
                    if event_user is not None:
                        # Update existing event registration
                        event_updates = [
                            {"row": event_user["Row"], "column": "First Name", "value": form.first_name.data},
                            {"row": event_user["Row"], "column": "Last Name", "value": form.last_name.data},
                            {"row": event_user["Row"], "column": "Membership Primary", "value": prim_email},
                            {"row": event_user["Row"], "column": "Membership Secondary", "value": sec_email},
                            {"row": event_user["Row"], "column": "Last Updated",
                             "value": str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p"))},
                            {"row": event_user["Row"], "column": "Ticket Type", "value": form.event_tickets.data}
                        ]

                        # Add event question responses
                        for question in event_obj.questions.split("\n"):
                            event_updates.append({
                                "row": event_user["Row"],
                                "column": question,
                                "value": form["event_" + question].data
                            })

                        execute_cell_updates(event_updates, event_obj.name)
                    else:
                        # Create new event registration
                        event_data = {
                            "Ticket Type": form.event_tickets.data
                        }

                        # Add event question responses
                        for question in event_obj.questions.split("\n"):
                            event_data[question] = form["event_" + question].data

                        user_data = {
                            "first_name": user["First Name"],
                            "last_name": user["Last Name"],
                            "primary_email": user["Primary Email"],
                            "secondary_email": user["Secondary Email"]
                        }

                        create_event_registration(event_obj.name, user_data, event_data)

                # PHASE 4: HANDLE SUBSCRIPTION STATUS (requires fresh data)
                updated_user = refresh_user_data(prim_email, sec_email)
                if updated_user:
                    # Determine subscription preferences
                    primary_subscription = form.primary_subscribe.data if updated_user["Primary Verified"] == "TRUE" else None
                    secondary_subscription = form.secondary_subscribe.data if updated_user["Secondary Verified"] == "TRUE" else None

                    update_subscription_status(
                        row_find,
                        primary_subscription,
                        secondary_subscription,
                        updated_user["Primary Verified"] == "TRUE",
                        updated_user["Secondary Verified"] == "TRUE"
                    )

                # PHASE 5: MARK COMPLETION
                update_completion_status(row_find)

                # PHASE 6: SEND CONFIRMATION EMAILS (Update-specific)
                final_user = refresh_user_data(prim_email, sec_email)
                if final_user:
                    subject = "I2G Membership Updated"
                    template_data = {
                        "event_url": event_url,
                        "update_url": update_url,
                        "first": final_user["First Name"],
                        "last": final_user["Last Name"],
                        "primary_email": final_user["Primary Email"],
                        "primary_verified": final_user["Primary Verified"],
                        "primary_subscribed": final_user["Primary Subscribed"],
                        "secondary_email": final_user["Secondary Email"],
                        "secondary_verified": final_user["Secondary Verified"],
                        "secondary_subscribed": final_user["Secondary Subscribed"],
                        "info_fields": info_fields,
                        "event_name": event_obj.name if event_obj is not None else None,
                        "event_fields": event_fields
                    }

                    # Send to verified emails only
                    if final_user["Primary Verified"] == "TRUE":
                        send_confirmation_email(
                            final_user["Primary Email"],
                            subject,
                            "update_receipt_email.html",
                            template_data
                        )

                    if final_user["Secondary Verified"] == "TRUE":
                        send_confirmation_email(
                            final_user["Secondary Email"],
                            subject,
                            "update_receipt_email.html",
                            template_data
                        )

            thread = Thread(target=execute_user_update)
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
