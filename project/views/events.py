import asyncio, traceback
from datetime import datetime
from threading import Thread

from gspread.cell import Cell
from flask import Blueprint, render_template, request, url_for, redirect, copy_current_request_context, abort, session, flash, get_flashed_messages
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField
from wtforms.validators import EqualTo, Email, InputRequired

from project import app, sh, wks, tz, get_wks_records, get_wks_columns
from project.models import event, edit_form
from project.utils.email import send_email
from project.utils.dynamic_fields import get_field, checkbox_get_choices
from project.utils.token import generate_token, confirm_token
from project.utils.event_utils import (
    make_sure, analyze_email_changes, calculate_verification_cell_updates, calculate_basic_user_updates,
    analyze_phone_number_changes, calculate_phone_verification_decision, 
    should_send_event_sms_confirmation, calculate_phone_updates
)
from project.utils.side_effect_helpers import (
    execute_cell_updates, send_verification_email, refresh_user_data,
    create_event_registration, update_subscription_status, update_completion_status,
    send_event_confirmation_emails, setup_event_phone_verification_session,
    start_event_phone_verification_process, send_event_sms_confirmation,
    extract_phone_data_from_event_form, create_event_registration_with_phone
)
from project.forms.registration_forms import NotEqualTo
from project.forms.update_forms import EmailForm
from project.forms.complete_registration_forms import CompleteRegistrationForm
from project.utils.twilio import split_number
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

            return render_template("event_instructions_sent.html")


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

    # Use the unified form that supports phone numbers
    class EventUpdateForm(CompleteRegistrationForm):
        pass

    # Add dynamic custom fields to the form
    for row in edit_form.query.all():
        setattr(EventUpdateForm, row.label, get_field(row))

    primary_temp = False
    if user["Primary Subscribed"] == "TRUE":
        primary_temp = True

    secondary_temp = False
    if user["Secondary Subscribed"] == "TRUE":
        secondary_temp = True

    # Phone data pre-population
    phone_temp = False
    if user.get("Phone number subscribed") == "TRUE":
        phone_temp = True
    
    country_code, number = "", ""
    if user.get("Phone Number"):
        try:
            country_code, number = split_number(str(user["Phone Number"]))
        except:
            # Handle malformed phone numbers gracefully
            country_code, number = "", ""

    person = {
        "first_name": user["First Name"],
        "last_name": user["Last Name"],
        "primary_email": user["Primary Email"],
        "confirm_primary": user["Primary Email"],
        "secondary_email": user["Secondary Email"],
        "confirm_secondary": user["Secondary Email"],
        "primary_subscribe": primary_temp,
        "secondary_subscribe": secondary_temp,
        "country_code": country_code,
        "phone_number": number,
        "confirm_phone_number": number,
        "phone_subscribe": phone_temp,
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

        setattr(EventUpdateForm, "register_event", BooleanField(register_event_label, default=True))
        # setattr(
        #     EventUpdateForm, "event_zoom_or_not",
        #     RadioField("Will you attend on Zoom or In-Person?",
        #                choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
        #                validators=[InputRequired(" ")]))
        setattr(
            EventUpdateForm, "event_tickets",
            RadioField("Ticket Type",
                       choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                       validators=[InputRequired(" ")]))

        for question in event_obj.questions.split("\n"):
            setattr(EventUpdateForm, "event_" + question, StringField(question, validators=[InputRequired(" ")]))

        if event_user is not None:
            # person["event_zoom_or_not"] = event_user["Will you attend on Zoom or In-Person?"]
            person["event_tickets"] = event_user["Ticket Type"]

            for question in event_obj.questions.split("\n"):
                if event_wks_columns[question] > len(event_user):
                    person["event_" + question] = ""
                else:
                    person["event_" + question] = event_user[question]

    form = EventUpdateForm(data=person)
    if hasattr(form, 'register_event'):
        form.register_event.render_kw = {"disabled": True}


    if request.method == "POST" and form.validate_on_submit():

        # Extract phone data first (needed for logging)
        # Check if phone fields were actually submitted in the form data
        # If not submitted, treat as empty (user wants to clear phone data)
        if 'country_code' in request.form or 'phone_number' in request.form:
            phone_data = extract_phone_data_from_event_form(form)
        else:
            # Phone fields not submitted - user wants to clear phone data
            phone_data = {
                "country_code": "",
                "phone_number": "",
                "phone_subscribe": False,
                "full_phone_number": ""
            }

        # LOG STUFF #
        path = f"/event-registration/{event_name}/{token}"
        first_name = form.first_name.data
        last_name = form.last_name.data
        primary_email = form.primary_email.data
        secondary_email = form.secondary_email.data
        phone_number = phone_data.get('full_phone_number', '')
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
        # Check if secondary_email was actually submitted in the form data
        # If not submitted, treat as empty (user wants to clear it)
        if 'secondary_email' in request.form:
            sec_email = form.secondary_email.data.lower() if form.secondary_email.data else ""
        else:
            sec_email = ""

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

            # PHASE 1: ANALYZE EMAIL AND PHONE CHANGES (Before background thread)
            email_decision = analyze_email_changes(user, prim_email, sec_email)

            phone_decision = analyze_phone_number_changes(
                user.get("Phone Number", ""),
                phone_data.get("country_code", ""),
                phone_data.get("phone_number", ""),
                wks_records,
                row_find
            )

            if phone_decision.error:
                return render_template("error3.html")

            needs_phone_verification = calculate_phone_verification_decision(
                user, 
                phone_decision,
                phone_data.get("phone_subscribe", False)
            )

            # PHASE 1.5: VALIDATE PHONE NUMBER (Don't block on failure)
            show_otp = False
            if needs_phone_verification:
                try:
                    start_event_phone_verification_process(phone_data.get('full_phone_number', ''))
                    show_otp = True
                except ValueError as e:
                    print(f"Phone validation failed: {str(e)}")
                    Thread(target=logger.log_background_error, args=(
                        f"/event-registration/{event_name}/{token}",
                        prim_email,
                        {
                            "error_type": "PhoneValidationError",
                            "error_message": f"Twilio validation failed: {str(e)}",
                            "stack_trace": traceback.format_exc()
                        }
                    )).start()
                    # Continue without phone verification

            # PHASE 1.6: START EXPIRY TIMERS (Main thread)
            from project.utils.side_effect_helpers import start_email_expiry_timer
            for email in email_decision.emails_needing_verification:
                start_email_expiry_timer(email)

            # PHASE 1.7: SETUP OTP SESSION (if needed)
            if show_otp:
                user_data = {
                    "first_name": form.first_name.data,
                    "last_name": form.last_name.data,
                    "primary_email": prim_email,
                    "secondary_email": sec_email,
                    "primary_verified": user["Primary Verified"],
                    "primary_subscribed": user["Primary Subscribed"],
                    "secondary_verified": user["Secondary Verified"],
                    "secondary_subscribed": user["Secondary Subscribed"],
                    "info_fields": info_fields,
                }
                
                event_data = {
                    "event_url": event_url,
                    "update_url": update_url,
                    "event_fields": event_fields,
                    "event_name": event_obj.name if event_obj else None,
                }
                
                setup_event_phone_verification_session(session, user_data, event_data, phone_data)

            @copy_current_request_context
            def execute_user_update():
                """Refactored function using separated logic and side effects"""
                try:
                    # PHASE 1: Analysis and validation now in main thread

                    # PHASE 2: CALCULATE REQUIRED UPDATES (Pure Logic)
                    # Get custom fields for form processing
                    custom_fields = [{"label": row.label, "field_type": row.field_type}
                                   for row in edit_form.query.all()]

                    # Prepare form data for processing (including phone data)
                    form_data = {
                        "first_name": form.first_name.data,
                        "last_name": form.last_name.data,
                        "primary_email": prim_email,
                        "secondary_email": sec_email,
                        "country_code": phone_data.get("country_code", ""),
                        "phone_number": phone_data.get("phone_number", ""),
                        "phone_subscribe": phone_data.get("phone_subscribe", False),
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
                    verification_updates = calculate_verification_cell_updates(user, email_decision, row_find)
                    phone_updates = calculate_phone_updates(user, form_data, phone_decision, row_find)

                    # PHASE 3: EXECUTE SIDE EFFECTS
                    
                    # 3.1: Execute membership database updates first
                    all_updates = basic_updates + verification_updates + phone_updates
                    execute_cell_updates(all_updates, "membership")

                    # 3.2: Send verification emails for new emails
                    for email in email_decision.emails_needing_verification:
                        send_verification_email(email, user["First Name"], user["Last Name"], start_expiry_timer=False)

                    # 3.3: Update event worksheet (ALWAYS complete this before phone verification)
                    if event_obj is not None:
                        if event_user is not None:
                            # Determine the correct phone number value based on phone decision
                            if phone_decision.clear:
                                event_phone_value = ""
                            else:
                                event_phone_value = phone_data.get('full_phone_number', '')
                            
                            # Update existing event registration
                            event_updates = [
                                {"row": event_user["Row"], "column": "First Name", "value": form.first_name.data},
                                {"row": event_user["Row"], "column": "Last Name", "value": form.last_name.data},
                                {"row": event_user["Row"], "column": "Membership Primary", "value": prim_email},
                                {"row": event_user["Row"], "column": "Membership Secondary", "value": sec_email},
                                {"row": event_user["Row"], "column": "Phone Number", "value": event_phone_value},
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
                                "first_name": form.first_name.data,
                                "last_name": form.last_name.data,
                                "primary_email": prim_email,
                                "secondary_email": sec_email
                            }

                            # For new event registrations, only pass phone data if not clearing
                            event_phone_data = None if phone_decision.clear else phone_data
                            create_event_registration_with_phone(event_obj.name, user_data, event_data, event_phone_data)

                    # PHASE 4: HANDLE SUBSCRIPTION STATUS (calculate from local state)
                    # Calculate final verification status from email decision
                    final_primary_verified = not email_decision.verification_status_updates.get("primary", False)
                    final_secondary_verified = not email_decision.verification_status_updates.get("secondary", False)

                    # Determine subscription preferences
                    primary_subscription = form.primary_subscribe.data if final_primary_verified else None
                    secondary_subscription = form.secondary_subscribe.data if final_secondary_verified else None

                    update_subscription_status(
                        row_find,
                        primary_subscription,
                        secondary_subscription,
                        final_primary_verified,
                        final_secondary_verified
                    )

                    # PHASE 5: MARK COMPLETION
                    update_completion_status(row_find)

                    # PHASE 6: SEND SMS CONFIRMATION (if applicable)
                    # Only send SMS for new event registrations, not updates
                    is_new_event_registration = event_user is None
                    if should_send_event_sms_confirmation(
                        user.get("Phone number verified", "FALSE"),
                        phone_data.get("phone_subscribe", False),
                        bool(phone_data.get("full_phone_number", "")),
                        event_obj.name if event_obj else None,
                        is_new_event_registration
                    ):
                        send_event_sms_confirmation(
                            phone_data.get("full_phone_number", ""),
                            event_obj.name
                        )

                    # PHASE 7: SEND CONFIRMATION EMAILS
                    # Build template data locally without fetching from sheets
                    phone_num = phone_data.get('full_phone_number', '')
                    phone_display = f"+{phone_num}" if phone_num and not str(phone_num).startswith("+") else phone_num

                    # Calculate phone verification status
                    if phone_decision.clear:
                        final_phone_verified = "FALSE"
                        final_phone_subscribed = "FALSE"
                    elif phone_decision.changed and needs_phone_verification:
                        final_phone_verified = "FALSE"
                        final_phone_subscribed = "TRUE" if phone_data.get("phone_subscribe", False) else "FALSE"
                    else:
                        final_phone_verified = user.get("Phone number verified", "FALSE")
                        final_phone_subscribed = "TRUE" if phone_data.get("phone_subscribe", False) else "FALSE"

                    local_user_data = {
                        "First Name": form.first_name.data,
                        "Last Name": form.last_name.data,
                        "Primary Email": prim_email,
                        "Primary Verified": "TRUE" if final_primary_verified else "FALSE",
                        "Primary Subscribed": "TRUE" if primary_subscription else "FALSE",
                        "Secondary Email": sec_email,
                        "Secondary Verified": "TRUE" if final_secondary_verified else "FALSE",
                        "Secondary Subscribed": "TRUE" if secondary_subscription else "FALSE",
                        "Phone Number": phone_display,
                        "Phone number verified": final_phone_verified,
                        "Phone number subscribed": final_phone_subscribed,
                    }

                    send_event_confirmation_emails(
                        local_user_data,
                        event_obj.name,
                        event_url,
                        update_url,
                        info_fields,
                        event_fields
                    )

                    # Return success
                    return {"status": "success"}
                    
                except Exception as e:
                    # Log comprehensive error details
                    logger.log_background_error(
                        f"/event-registration/{event_name}/{token}",
                        prim_email,
                        {
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "stack_trace": traceback.format_exc()
                        }
                    )
                    return {"status": "error", "message": str(e)}

            # Execute user update in BACKGROUND THREAD
            thread = Thread(target=execute_user_update)
            thread.start()

            # Return immediately
            if show_otp:
                return redirect(url_for("confirm.otp"))
            else:
                # Calculate final state for template (from main thread decisions)
                final_primary_verified = not email_decision.verification_status_updates.get("primary", False)
                final_secondary_verified = not email_decision.verification_status_updates.get("secondary", False)
                
                # Calculate phone status
                if phone_decision.clear:
                    final_phone_verified = "FALSE"
                    final_phone_subscribed = "FALSE"
                else:
                    final_phone_verified = user.get("Phone number verified", "FALSE")
                    final_phone_subscribed = "TRUE" if phone_data.get("phone_subscribe", False) else "FALSE"
                
                return render_template("successfully_registered.html",
                                      event_url=event_url,
                                      update_url=update_url,
                                      first=form.first_name.data,
                                      last=form.last_name.data,
                                      primary_email=form.primary_email.data,
                                      primary_verified="TRUE" if final_primary_verified else "FALSE",
                                      primary_subscribed=primary_subscribed,
                                      secondary_email=form.secondary_email.data,
                                      secondary_verified="TRUE" if final_secondary_verified else "FALSE",
                                      secondary_subscribed=secondary_subscribed,
                                      phone_number=phone_data.get('full_phone_number', ''),
                                      phone_number_verified=final_phone_verified,
                                      phone_subscribed=final_phone_subscribed,
                                      info_fields=info_fields,
                                      event_name=event_obj.name if event_obj is not None else None,
                                      event_fields=event_fields)

    else:
        # GET request - clear any stale flash messages from previous sessions
        get_flashed_messages()  # Consume and discard any existing flash messages
        # if form.errors:
        #     print(f"errors: {form.errors}")
        return render_template("event_registration.html", form=form, token=token, event=event_obj)
