import asyncio, time, traceback
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import (
    Blueprint,
    render_template,
    url_for,
    request,
    redirect,
    copy_current_request_context,
    session,
    flash,
    get_flashed_messages,
)
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField
from wtforms.validators import Optional
from project import app, sh, wks, tz, get_wks_records, get_wks_columns
from project.models import edit_form, event
from project.utils.email import send_email
from project.utils.dynamic_fields import get_field, checkbox_get_choices
from project.utils.token import generate_token, confirm_token
from project.services.logging_service import Logger
from project.utils.registration_utils import (
    analyze_complete_registration_conflicts,
    calculate_new_user_creation,
    calculate_event_registration_from_complete,
    analyze_phone_number_conflicts,
    calculate_registration_method,
    should_trigger_phone_verification,
    calculate_phone_registration_data,
)
from project.utils.side_effect_helpers import (
    execute_cell_updates,
    send_verification_email,
    send_deletion_notice_email,
    create_complete_user_registration,
    create_event_registration,
    create_event_registration_with_phone,
    send_complete_registration_confirmation_email,
    start_phone_verification_process,
    setup_otp_verification_session,
    send_event_sms_confirmation,
)
from project.forms.registration_forms import NotEqualTo, RegistrationForm
from project.forms.complete_registration_forms import CompleteRegistrationForm

registration_blueprint = Blueprint(
    "registration",
    __name__,
    template_folder="../templates/membership/registration",
    url_prefix=app.config["URL_PREFIX"],
)

logger = Logger()


@registration_blueprint.route("/signup", methods=["GET", "POST"])
def register():
    # Use the unified form that includes phone fields
    form = CompleteRegistrationForm()

    cells = []
    event_cells = []

    global can_register
    can_register = True

    if request.method == "POST" and form.validate_on_submit():
        Thread(
            target=logger.log_registration,
            args=(
                "/signup",
                form.first_name.data,
                form.last_name.data,
                form.primary_email.data,
                form.secondary_email.data,
            ),
        ).start()

        wks_records = get_wks_records(wks)
        wks_columns = get_wks_columns(wks)

        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

        if event_obj is not None:
            event_wks = sh.worksheet(event_obj.name)
            event_wks_records = get_wks_records(event_wks)
            event_wks_columns = get_wks_columns(event_wks)

        prim_email = request.form["primary_email"].lower()
        sec_email = request.form["secondary_email"].lower()

        # Extract phone number data (optional)
        phone_number = ""
        phone_subscribe_flag = False
        if (
                hasattr(form, "country_code")
                and hasattr(form, "phone_number")
                and form.country_code.data
                and form.phone_number.data
        ):
            country_code_input = str(form.country_code.data).strip()
            number_input = (
                str(form.phone_number.data).strip().replace(" ", "").replace("-", "")
            )
            # Ensure country code starts with + for proper formatting
            if country_code_input and not country_code_input.startswith("+"):
                country_code_input = "+" + country_code_input
            # Combine and ensure + is at the very start
            phone_number = country_code_input + number_input
            if phone_number and not phone_number.startswith("+"):
                phone_number = "+" + phone_number
            # phone_subscribe_flag = bool(
            #     getattr(form, "phone_subscribe", None) and form.phone_subscribe.data
            # )

        async def search_prim_in_prim_col():
            user_prim1 = [
                row for row in wks_records if row["Primary Email"] == prim_email
            ]
            if user_prim1:
                user_prim1 = user_prim1[0]
                row_prim1 = user_prim1["Row"]
            else:
                return

            if user_prim1 is not None and user_prim1["Primary Expired"] == "TRUE":
                cells.append(Cell(row_prim1, wks_columns["Primary Email"], ""))

                if event_obj is not None:
                    event_user = [
                        row
                        for row in event_wks_records
                        if row["Membership Primary"] == prim_email
                    ]
                    if event_user:
                        event_cells.append(
                            Cell(
                                event_user[0]["Row"],
                                event_wks_columns["Membership Primary"],
                                "",
                            )
                        )

                if (
                        user_prim1["Secondary Email"]
                        and user_prim1["Secondary Email"].strip() != ""
                        and user_prim1["Secondary Verified"] == "TRUE"
                ):
                    html = render_template(
                        "deleting_email.html",
                        first=user_prim1["First Name"],
                        last=user_prim1["Last Name"],
                        email=user_prim1["Primary Email"],
                    )
                    thread = Thread(
                        target=send_email,
                        args=(
                            user_prim1["Secondary Email"],
                            app.config["REMOVE_SUBJECT"],
                            html,
                        ),
                    )
                    thread.start()

            elif user_prim1 is not None and user_prim1["Primary Expired"] == "FALSE":
                global can_register
                can_register = False
                if user_prim1["Primary Verified"] == "TRUE":
                    token = generate_token(user_prim1["Primary Email"])
                    update_url = url_for(
                        "update.update_info", token=token, _external=True
                    )
                    update_html = render_template(
                        "update_email.html",
                        first=user_prim1["First Name"],
                        last=user_prim1["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(
                        target=send_email,
                        args=(
                            user_prim1["Primary Email"],
                            app.config["UPDATE_SUBJECT"],
                            update_html,
                        ),
                    )
                    thread.start()

        async def search_prim_in_sec_col():
            user_prim2 = [
                row for row in wks_records if row["Secondary Email"] == prim_email
            ]
            if user_prim2:
                user_prim2 = user_prim2[0]
                row_prim2 = user_prim2["Row"]
            else:
                return

            if user_prim2 is not None and user_prim2["Secondary Expired"] == "TRUE":
                cells.append(Cell(row_prim2, wks_columns["Secondary Email"], ""))

                if event_obj is not None:
                    event_user = [
                        row
                        for row in event_wks_records
                        if row["Membership Secondary"] == prim_email
                    ]
                    if event_user:
                        event_cells.append(
                            Cell(
                                event_user[0]["Row"],
                                event_wks_columns["Membership Secondary"],
                                "",
                            )
                        )

                if (
                        user_prim2["Primary Email"]
                        and user_prim2["Primary Email"].strip() != ""
                        and user_prim2["Primary Verified"] == "TRUE"
                ):
                    html = render_template(
                        "deleting_email.html",
                        first=user_prim2["First Name"],
                        last=user_prim2["Last Name"],
                        email=user_prim2["Secondary Email"],
                    )
                    thread = Thread(
                        target=send_email,
                        args=(
                            user_prim2["Primary Email"],
                            app.config["REMOVE_SUBJECT"],
                            html,
                        ),
                    )
                    thread.start()

            elif user_prim2 is not None and user_prim2["Secondary Expired"] == "FALSE":
                global can_register
                can_register = False
                if user_prim2["Secondary Verified"] == "TRUE":
                    token = generate_token(user_prim2["Secondary Email"])
                    update_url = url_for(
                        "update.update_info", token=token, _external=True
                    )
                    update_html = render_template(
                        "update_email.html",
                        first=user_prim2["First Name"],
                        last=user_prim2["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(
                        target=send_email,
                        args=(
                            user_prim2["Secondary Email"],
                            app.config["UPDATE_SUBJECT"],
                            update_html,
                        ),
                    )
                    thread.start()

        async def search_sec_in_prim_col():
            # Only search if secondary email is not empty
            if not sec_email or sec_email.strip() == "":
                return
            user_sec1 = [
                row for row in wks_records if row["Primary Email"] == sec_email
            ]
            if user_sec1:
                user_sec1 = user_sec1[0]
                row_sec1 = user_sec1["Row"]
            else:
                return

            if user_sec1 is not None and user_sec1["Primary Expired"] == "TRUE":
                cells.append(Cell(row_sec1, wks_columns["Primary Email"], ""))

                if event_obj is not None:
                    event_user = [
                        row
                        for row in event_wks_records
                        if row["Membership Primary"] == sec_email
                    ]
                    if event_user:
                        event_cells.append(
                            Cell(
                                event_user[0]["Row"],
                                event_wks_columns["Membership Primary"],
                                "",
                            )
                        )

                if (
                        user_sec1["Secondary Email"]
                        and user_sec1["Secondary Email"].strip() != ""
                        and user_sec1["Secondary Verified"] == "TRUE"
                ):
                    html = render_template(
                        "deleting_email.html",
                        first=user_sec1["First Name"],
                        last=user_sec1["Last Name"],
                        email=user_sec1["Primary Email"],
                    )
                    thread = Thread(
                        target=send_email,
                        args=(
                            user_sec1["Secondary Email"],
                            app.config["REMOVE_SUBJECT"],
                            html,
                        ),
                    )
                    thread.start()

            elif user_sec1 is not None and user_sec1["Primary Expired"] == "FALSE":
                global can_register
                can_register = False
                if user_sec1["Primary Verified"] == "TRUE":
                    token = generate_token(user_sec1["Primary Email"])
                    update_url = url_for(
                        "update.update_info", token=token, _external=True
                    )
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec1["First Name"],
                        last=user_sec1["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(
                        target=send_email,
                        args=(
                            user_sec1["Primary Email"],
                            app.config["UPDATE_SUBJECT"],
                            update_html,
                        ),
                    )
                    thread.start()

        async def search_sec_in_sec_col():
            # Only search if secondary email is not empty
            if not sec_email or sec_email.strip() == "":
                return
            user_sec2 = [
                row for row in wks_records if row["Secondary Email"] == sec_email
            ]
            if user_sec2:
                user_sec2 = user_sec2[0]
                row_sec2 = user_sec2["Row"]
            else:
                return

            if user_sec2 is not None and user_sec2["Secondary Expired"] == "TRUE":
                cells.append(Cell(row_sec2, wks_columns["Secondary Email"], ""))

                if event_obj is not None:
                    event_user = [
                        row
                        for row in event_wks_records
                        if row["Membership Secondary"] == sec_email
                    ]
                    if event_user:
                        event_cells.append(
                            Cell(
                                event_user[0]["Row"],
                                event_wks_columns["Membership Secondary"],
                                "",
                            )
                        )

                if (
                        user_sec2["Primary Email"]
                        and user_sec2["Primary Email"].strip() != ""
                        and user_sec2["Primary Verified"] == "TRUE"
                ):
                    html = render_template(
                        "deleting_email.html",
                        first=user_sec2["First Name"],
                        last=user_sec2["Last Name"],
                        email=user_sec2["Secondary Email"],
                    )
                    thread = Thread(
                        target=send_email,
                        args=(
                            user_sec2["Primary Email"],
                            app.config["REMOVE_SUBJECT"],
                            html,
                        ),
                    )
                    thread.start()

            elif user_sec2 is not None and user_sec2["Secondary Expired"] == "FALSE":
                global can_register
                can_register = False
                if user_sec2["Secondary Verified"] == "TRUE":
                    token = generate_token(user_sec2["Secondary Email"])
                    update_url = url_for(
                        "update.update_info", token=token, _external=True
                    )
                    update_html = render_template(
                        "update_email.html",
                        first=user_sec2["First Name"],
                        last=user_sec2["Last Name"],
                        update_url=update_url,
                    )
                    thread = Thread(
                        target=send_email,
                        args=(
                            user_sec2["Secondary Email"],
                            app.config["UPDATE_SUBJECT"],
                            update_html,
                        ),
                    )
                    thread.start()

        async def update_sheet():
            if len(cells) > 0:
                wks.update_cells(cells)

            if len(event_cells) > 0:
                event_wks.update_cells(event_cells)

        async def main():
            await asyncio.gather(
                search_prim_in_prim_col(),
                search_prim_in_sec_col(),
                search_sec_in_prim_col(),
                search_sec_in_sec_col(),
                update_sheet(),
            )

        asyncio.run(main())

        if not can_register:
            return render_template("error1.html")
        else:

            @copy_current_request_context
            def can_register():
                user = ["" for i in range(len(wks_columns))]

                user[wks_columns["Order"] - 1] = (
                    int(wks.col_values(wks_columns["Order"])[-1]) + 1
                    if wks.col_values(wks_columns["Order"])[-1].isdigit()
                    else 1
                )
                user[wks_columns["First Name"] - 1] = form.first_name.data
                user[wks_columns["Last Name"] - 1] = form.last_name.data
                user[wks_columns["When Started"] - 1] = str(
                    datetime.now(tz)
                    .replace(second=0, microsecond=0)
                    .strftime("%Y-%m-%d %I:%M %p")
                )
                user[wks_columns["Last Updated"] - 1] = str(
                    datetime.now(tz)
                    .replace(second=0, microsecond=0)
                    .strftime("%Y-%m-%d %I:%M %p")
                )
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
                # Write phone data if provided
                try:
                    if phone_number:
                        user[wks_columns["Phone Number"] - 1] = phone_number
                        user[wks_columns["Phone number verified"] - 1] = "FALSE"
                        user[wks_columns["Phone number subscribed"] - 1] = (
                            "TRUE" if phone_subscribe_flag else "FALSE"
                        )
                except Exception:
                    # If phone columns are missing, skip without failing signup
                    pass
                user[wks_columns["Info Completed"] - 1] = "FALSE"

                wks.append_row(user)

                p_token = generate_token(prim_email)
                p_confirm_url = url_for(
                    "registration.confirm", token=p_token, _external=True
                )
                p_html = render_template(
                    "verify_email.html",
                    first=form.first_name.data,
                    last=form.last_name.data,
                    confirm_url=p_confirm_url,
                )

                s_token = generate_token(sec_email)
                s_confirm_url = url_for(
                    "registration.confirm", token=s_token, _external=True
                )
                s_html = render_template(
                    "verify_email.html",
                    first=form.first_name.data,
                    last=form.last_name.data,
                    confirm_url=s_confirm_url,
                )

                send_email(prim_email, app.config["VERIF_SUBJECT"], p_html)
                if sec_email and sec_email.strip() != "":
                    send_email(sec_email, app.config["VERIF_SUBJECT"], s_html)

                def expiry_timer():
                    time.sleep(app.config["EXPIRY_TIMER"])
                    wks_records = get_wks_records(wks)
                    wks_columns = get_wks_columns(wks)
                    row = [
                        row for row in wks_records if row["Primary Email"] == prim_email
                    ]
                    if row:
                        row = row[0]
                        if row["Primary Verified"] == "FALSE":
                            wks.update_cell(
                                row["Row"], wks_columns["Primary Expired"], "TRUE"
                            )
                        if row["Secondary Verified"] == "FALSE":
                            wks.update_cell(
                                row["Row"], wks_columns["Secondary Expired"], "TRUE"
                            )

                thread = Thread(target=expiry_timer)
                thread.start()

            # Before creating the row, if phone present: check conflicts and decide OTP
            needs_phone_verification = False
            if phone_number:
                # Re-fetch records for the latest data
                wks_records_conf = get_wks_records(wks)
                # Phone conflict check
                phone_conflict = analyze_phone_number_conflicts(
                    wks_records_conf, phone_number
                )
                if not phone_conflict["can_proceed"]:
                    return render_template("error3.html")

                # Decide verification need
                registration_method = calculate_registration_method(
                    has_secondary_email=bool(sec_email.strip()), has_phone_number=True
                )
                needs_phone_verification = should_trigger_phone_verification(
                    registration_method, phone_number
                )

            # If OTP needed, validate phone BEFORE creating user
            if phone_number and needs_phone_verification:
                # Validate phone number FIRST
                try:
                    start_phone_verification_process(phone_number)
                except ValueError as e:
                    # Phone number validation failed - show error to user
                    flash(f"Phone number validation failed: {str(e)}", "error")
                    return render_template("register_form.html", form=form)

                # Phone validation passed - prepare session data
                user_data = {
                    "first_name": form.first_name.data,
                    "last_name": form.last_name.data,
                    "primary_email": prim_email,
                    "primary_verified": "FALSE",
                    "primary_subscribed": "FALSE",
                    "secondary_email": sec_email,
                    "secondary_verified": "FALSE",
                    "secondary_subscribed": "FALSE",
                    "update_url": url_for(
                        "update.update_info",
                        token=generate_token(prim_email),
                        _external=True,
                    ),
                    "info_fields": {},
                }

                event_data = None

                phone_data = {
                    "phone_number": phone_number,
                    "phone_subscribe": "TRUE" if phone_subscribe_flag else "FALSE",
                }

                # Stash origin markers for OTP routing
                session["update"] = "FALSE"
                session["event_reg"] = "no"
                session["origin"] = "signup"

                setup_otp_verification_session(
                    session, user_data, event_data, phone_data
                )

            # Append row in background (AFTER phone validation if needed)
            thread = Thread(target=can_register)
            thread.start()

            # If phone verification was needed, redirect to OTP
            if phone_number and needs_phone_verification:
                return redirect(url_for("confirm.otp"))

            return render_template("instructions_sent.html")

    else:
        # GET request - clear any stale flash messages from previous sessions
        get_flashed_messages()  # Consume and discard any existing flash messages
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
            verif_key = (
                "Primary Verified"
                if user["Primary Email"] == email
                else "Secondary Verified"
            )

    if user is None:
        return redirect(
            url_for("registration.resend_page", token=token, _external=True)
        )

    elif user[verif_key] == "TRUE" and user["Info Completed"] == "TRUE":
        return render_template("already_confirmed.html")

    else:

        def update_sheet(wks_records, wks_columns):
            user_find = [row for row in wks_records if row["Primary Email"] == email]
            if not user_find:
                user_find = [
                    row for row in wks_records if row["Secondary Email"] == email
                ][0]
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

            event_obj = (
                event.query.filter_by(live=True).order_by(event.id.desc()).first()
            )

            if event_obj is not None:
                event_wks = sh.worksheet(event_obj.name)
                event_wks_records = get_wks_records(event_wks)
                event_wks_columns = get_wks_columns(event_wks)
                event_url = url_for(
                    "events.event_register",
                    event_name=event_obj.name.replace(" ", "-"),
                    token=token,
                    _external=True,
                )

                async def query_event_prim_col():
                    return [
                        row
                        for row in event_wks_records
                        if row["Membership Primary"] == email
                    ]

                async def query_event_sec_col():
                    return [
                        row
                        for row in event_wks_records
                        if row["Membership Secondary"] == email
                    ]

                async def main():
                    return await asyncio.gather(
                        query_event_prim_col(), query_event_sec_col()
                    )

                event_user = asyncio.run(main())
                event_user = (
                    event_user[0][0]
                    if event_user[0]
                    else event_user[1][0]
                    if event_user[1]
                    else None
                )

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
                    # event_fields["Will you attend on Zoom or In-Person?"] = event_user["Will you attend on Zoom or In-Person?"]
                    event_fields["Ticket Type"] = event_user["Ticket Type"]

                    for question in event_obj.questions.split("\n"):
                        if event_wks_columns[question] > len(event_user):
                            event_fields[question] = ""
                        else:
                            event_fields[question] = event_user[question]

            subject = "I2G Membership Completed"
            html = render_template(
                "info_receipt_email.html",
                event_url=event_url,
                update_url=update_url,
                first=user["First Name"],
                last=user["Last Name"],
                primary_verified=primary_verified,
                secondary_verified=secondary_verified,
                primary_subscribed=primary_subscribed,
                secondary_subscribed=secondary_subscribed,
                phone_number=str(user.get("Phone Number", "") or ""),
                phone_number_verified=user.get("Phone number verified", "FALSE"),
                phone_subscribed=True if user.get("Phone number subscribed", "FALSE") == "TRUE" else False,
                info_fields=info_fields,
                event_fields=event_fields,
                event_name=event_obj.name if event_obj is not None else None,
            )
            send_email(email, subject, html)

            return render_template(
                "thanks_confirming.html",
                event_url=event_url,
                update_url=update_url,
                first=user["First Name"],
                last=user["Last Name"],
                primary_verified=primary_verified,
                secondary_verified=secondary_verified,
                primary_subscribed=primary_subscribed,
                secondary_subscribed=secondary_subscribed,
                phone_number=str(user.get("Phone Number", "") or ""),
                phone_number_verified=user.get("Phone number verified", "FALSE"),
                phone_subscribed=True if user.get("Phone number subscribed", "FALSE") == "TRUE" else False,
                info_fields=info_fields,
                event_name=event_obj.name if event_obj is not None else None,
                event_fields=event_fields,
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
        event_url = url_for(
            "events.event_register",
            event_name=event_obj.name.replace(" ", "-"),
            token=token,
            _external=True,
        )

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
        submit = SubmitField("Submit")

    person = {}

    for row in edit_form.query.all():
        setattr(InformationForm, row.label, get_field(row))

        if event_obj is not None:
            async def query_event_prim_col():
                return [
                    row
                    for row in event_wks_records
                    if row["Membership Primary"] == email
                ]

            async def query_event_sec_col():
                return [
                    row
                    for row in event_wks_records
                    if row["Membership Secondary"] == email
                ]

            async def main():
                return await asyncio.gather(
                    query_event_prim_col(), query_event_sec_col()
                )

            event_user = asyncio.run(main())
            event_user = (
                event_user[0][0]
                if event_user[0]
                else event_user[1][0]
                if event_user[1]
                else None
            )
            is_new_event_registration = event_user is None

        if event_user is not None:
            register_event_label = "Update " + event_obj.name + " registration?"
        else:
            register_event_label = "Also register for " + event_obj.name + "?"

        setattr(
            InformationForm,
            "register_event",
            BooleanField(register_event_label, default=True),
        )
        # setattr(
        #     InformationForm, "event_zoom_or_not",
        #     RadioField("Will you attend on Zoom or In-Person?",
        #                choices=[("Zoom", "Zoom"), ("In-Person", "In-Person"), ("Both", "Both")],
        #                validators=[Optional()]))
        setattr(
            InformationForm,
            "event_tickets",
            RadioField(
                "Ticket Type",
                choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                validators=[Optional()],
            ),
        )

        for question in event_obj.questions.split("\n"):
            setattr(InformationForm, "event_" + question, StringField(question))

        if event_user is not None:
            person["register_event"] = True
            # person["event_zoom_or_not"] = event_user["Will you attend on Zoom or In-Person?"]
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
        def update_sheet():
            cell_find = [row for row in wks_records if row["Primary Email"] == email]
            if not cell_find:
                cell_find = [
                    row for row in wks_records if row["Secondary Email"] == email
                ]

            row_find = cell_find[0]["Row"]

            for row in edit_form.query.all():
                if row.field_type == "Checkbox":
                    vals = []
                    choices = checkbox_get_choices(row.options)
                    for key in request.form.getlist(row.label):
                        vals.append(choices[int(key)][1])
                    cells.append(
                        Cell(row_find, wks_columns[row.label], "\n".join(vals))
                    )
                else:
                    cells.append(
                        Cell(row_find, wks_columns[row.label], request.form[row.label])
                    )

            cells.append(Cell(row_find, wks_columns["Info Completed"], "TRUE"))

        if event_obj is not None:
            if form.register_event.data:
                if event_user is not None:
                    event_cells.append(
                        Cell(
                            event_user["Row"],
                            event_wks_columns["Last Updated"],
                            str(
                                datetime.now(tz)
                                .replace(second=0, microsecond=0)
                                .strftime("%Y-%m-%d %I:%M %p")
                            ),
                        )
                    )
                    # event_cells.append(
                    #     Cell(event_user["Row"], event_wks_columns["Will you attend on Zoom or In-Person?"], form.event_zoom_or_not.data))
                    event_cells.append(
                        Cell(
                            event_user["Row"],
                            event_wks_columns["Ticket Type"],
                            form.event_tickets.data,
                        )
                    )

                    # Add phone number to existing event registration if user has one
                    if "Phone Number" in event_wks_columns and user.get("Phone Number"):
                        phone_value = str(user["Phone Number"])
                        if phone_value and not phone_value.startswith("+"):
                            phone_value = "+" + phone_value
                        event_cells.append(
                            Cell(
                                event_user["Row"],
                                event_wks_columns["Phone Number"],
                                phone_value,
                            )
                        )

                    for question in event_obj.questions.split("\n"):
                        event_cells.append(
                            Cell(
                                event_user["Row"],
                                event_wks_columns[question],
                                form["event_" + question].data,
                            )
                        )

                else:
                    row = ["" for i in range(len(event_wks.row_values(1)))]

                    row[event_wks_columns["Order"] - 1] = (
                        int(event_wks.col_values(1)[-1]) + 1
                        if event_wks.col_values(1)[-1].isdigit()
                        else 1
                    )
                    row[event_wks_columns["First Name"] - 1] = user["First Name"]
                    row[event_wks_columns["Last Name"] - 1] = user["Last Name"]
                    row[event_wks_columns["When Started"] - 1] = str(
                        datetime.now(tz)
                        .replace(second=0, microsecond=0)
                        .strftime("%Y-%m-%d %I:%M %p")
                    )
                    row[event_wks_columns["Last Updated"] - 1] = str(
                        datetime.now(tz)
                        .replace(second=0, microsecond=0)
                        .strftime("%Y-%m-%d %I:%M %p")
                    )
                    row[event_wks_columns["Membership Primary"] - 1] = user[
                        "Primary Email"
                    ]
                    row[event_wks_columns["Membership Secondary"] - 1] = user[
                        "Secondary Email"
                    ]
                    row[event_wks_columns["Ticket Type"] - 1] = form.event_tickets.data
                    # row[event_wks_columns["Will you attend on Zoom or In-Person?"] - 1] = form.event_zoom_or_not.data

                    # Add phone number to new event registration if user has one
                    if "Phone Number" in event_wks_columns and user.get("Phone Number"):
                        phone_value = str(user["Phone Number"])
                        if phone_value and not phone_value.startswith("+"):
                            phone_value = "+" + phone_value
                        row[event_wks_columns["Phone Number"] - 1] = phone_value

                    for question in event_obj.questions.split("\n"):
                        row[event_wks_columns[question] - 1] = form[
                            "event_" + question
                            ].data

                    event_wks.append_row(row)

            if len(cells) > 0:
                wks.update_cells(cells)

            if len(event_cells) > 0:
                event_wks.update_cells(event_cells)

            # If a new event registration just happened and phone is verified+subscribed, send SMS
            try:
                if event_obj is not None and is_new_event_registration:
                    # Get the current user's data by finding the user who just completed the info form
                    # Use the email from the token to find the correct user
                    current_user_email = email  # This is the email from the token
                    fresh_user_records = get_wks_records(wks)

                    # Find the user by the email that was used to access this info form
                    current_user = None
                    for row in fresh_user_records:
                        if (
                                row["Primary Email"] == current_user_email
                                or row["Secondary Email"] == current_user_email
                        ):
                            current_user = row
                            break

                    # if current_user:
                    #     current_phone = str(current_user.get("Phone Number", "") or "")
                    #     current_phone_verified = current_user.get(
                    #         "Phone number verified", "FALSE"
                    #     )
                    #     current_phone_subscribed = (
                    #         current_user.get("Phone number subscribed", "FALSE")
                    #         == "TRUE"
                    #     )

                    #     if (
                    #         current_phone
                    #         and current_phone_verified == "TRUE"
                    #         and current_phone_subscribed
                    #     ):
                    #         send_event_sms_confirmation(current_phone, event_obj.name)
            except Exception as e:
                print(f"Error sending event SMS after info form: {e}")

            subject = "I2G Membership Completed"
            html = render_template(
                "info_receipt_email.html",
                event_url=event_url,
                update_url=update_url,
                first=user["First Name"],
                last=user["Last Name"],
                phone_number=str(user.get("Phone Number", "") or ""),
                phone_number_verified=user.get("Phone number verified", "FALSE"),
                phone_subscribed=True
                if user.get("Phone number subscribed", "FALSE") == "TRUE"
                else False,
                primary_email=user["Primary Email"],
                primary_verified=user["Primary Verified"],
                primary_subscribed=user["Primary Subscribed"],
                secondary_email=user["Secondary Email"],
                secondary_verified=user["Secondary Verified"],
                secondary_subscribed=user["Secondary Subscribed"],
                info_fields=info_fields,
                event_name=event_obj.name if event_obj is not None else None,
                event_fields=event_fields,
            )

            send_email(email, subject, html)

        thread = Thread(target=update_sheet)
        thread.start()

        return render_template(
            "receipt.html",
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
            phone_number=str(user.get("Phone Number", "") or ""),
            phone_number_verified=user.get("Phone number verified", "FALSE"),
            phone_subscribed=True
            if user.get("Phone number subscribed", "FALSE") == "TRUE"
            else False,
            info_fields=info_fields,
            event_name=event_obj.name if event_obj is not None else None,
            event_fields=event_fields,
        )

    else:
        return render_template("info_form.html", form=form, token=token, user=user)


@registration_blueprint.route("/full-registration/<token>", methods=["GET", "POST"])
def complete_registration(token):
    email: str = confirm_token(token, None)

    if not email:
        return render_template("error5.html")

    email = email.lower()

    # Get initial data
    wks_records = get_wks_records(wks)
    event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()

    # Check if user already exists (should not for complete registration)
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

    # Build dynamic form by adding custom fields to the base formin

    # Add custom fields
    for row in edit_form.query.all():
        setattr(CompleteRegistrationForm, row.label, get_field(row))

    # Add event fields if there's a live event
    if event_obj is not None:
        setattr(
            CompleteRegistrationForm,
            "register_event",
            BooleanField("Also register for " + event_obj.name + "?", default=True),
        )
        setattr(
            CompleteRegistrationForm,
            "event_tickets",
            RadioField(
                "Ticket Type",
                choices=[(ticket, ticket) for ticket in event_obj.tickets.split("\n")],
                validators=[Optional()],
            ),
        )

        for question in event_obj.questions.split("\n"):
            setattr(
                CompleteRegistrationForm, "event_" + question, StringField(question)
            )

    # Pre-populate form with primary email from token
    person = {"primary_email": email, "confirm_primary": email}
    form = CompleteRegistrationForm(data=person)
    form.primary_email.render_kw = {"readonly": True}
    form.confirm_primary.render_kw = {"readonly": True}

    if request.method == "POST" and form.validate_on_submit():
        # Extract form data first for logging
        prim_email = form.primary_email.data.lower()
        sec_email = form.secondary_email.data.lower()

        # Extract phone number for logging
        phone_number = ""
        if form.country_code.data and form.phone_number.data:
            phone_number = form.country_code.data + form.phone_number.data

        # Log the registration attempt
        register_event_str = (
            "Register Event: " + str(form.register_event.data)
            if event_obj is not None
            else "No Event"
        )
        Thread(
            target=logger.log_complete_registration,
            args=(
                "/full-registration/<token>",
                form.first_name.data,
                form.last_name.data,
                form.primary_email.data,
                form.secondary_email.data,
                phone_number,
                register_event_str,
            ),
        ).start()

        # PHASE 1: ANALYZE CONFLICTS (Pure Logic) - Do this BEFORE background thread
        wks_records = get_wks_records(wks)

        # 1.1: Email conflict analysis
        conflict_decision = analyze_complete_registration_conflicts(
            wks_records, prim_email, sec_email
        )

        if not conflict_decision.can_proceed:
            return render_template("error1.html")

        # 1.2: Phone number validation and conflict analysis
        # Check for phone number conflicts
        phone_conflict = analyze_phone_number_conflicts(wks_records, phone_number)
        if not phone_conflict["can_proceed"]:
            return render_template("error3.html")  # Phone already exists

        # 1.3: Calculate registration method and determine verification needs
        registration_method = calculate_registration_method(
            has_secondary_email=bool(sec_email.strip()),
            has_phone_number=bool(phone_number.strip()),
        )

        needs_phone_verification = should_trigger_phone_verification(
            registration_method, phone_number
        )

        # EXTRACT ALL FORM DATA BEFORE THREAD (to avoid thread-safety issues with form object)
        # Get custom fields for form processing
        custom_fields = [
            {"label": row.label, "field_type": row.field_type}
            for row in edit_form.query.all()
        ]

        # Prepare form data for processing
        form_data = {
            "first_name": form.first_name.data,
            "last_name": form.last_name.data,
            "primary_email": prim_email,
            "secondary_email": sec_email,
            "primary_subscribe": form.primary_subscribe.data,
            "secondary_subscribe": form.secondary_subscribe.data,
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

        # Add phone data if provided
        if phone_number:
            phone_form_data = {
                "country_code": form.country_code.data,
                "phone_number": form.phone_number.data,
            }
            phone_data_calc = calculate_phone_registration_data(phone_form_data)
            form_data["phone_data"] = phone_data_calc

            # Also create phone data in the format expected by event registration
            form_data["event_phone_data"] = {
                "country_code": form.country_code.data,
                "phone_number": form.phone_number.data,
                "full_phone_number": phone_number,  # Use the already-calculated full number
            }

        # Extract event registration data
        register_for_event = event_obj is not None and form.register_event.data
        if register_for_event:
            event_questions = event_obj.questions.split("\n")
            form_data["event_tickets"] = form.event_tickets.data
            for question in event_questions:
                form_data[f"event_{question}"] = form[f"event_{question}"].data

        # PHASE 1.3: VALIDATE PHONE NUMBER WITH TWILIO (Don't block on failure)
        show_otp = False
        if needs_phone_verification:
            try:
                start_phone_verification_process(phone_number)
                show_otp = True  # Validation successful, show OTP page
            except ValueError as e:
                # Log error but don't block registration
                print(f"Phone validation failed for {phone_number}: {str(e)}")
                Thread(
                    target=logger.log_background_error,
                    args=(
                        "/full-registration/<token>",
                        prim_email,
                        {
                            "error_type": "PhoneValidationError",
                            "error_message": f"Twilio validation failed: {str(e)}",
                            "stack_trace": traceback.format_exc(),
                        },
                    ),
                ).start()
                # Continue without phone verification

        # PHASE 1.4: START EXPIRY TIMER FOR SECONDARY EMAIL (Main thread)
        if sec_email and sec_email.strip():
            from project.utils.side_effect_helpers import start_email_expiry_timer

            start_email_expiry_timer(sec_email)

        # PHASE 1.5: PREPARE DATA FOR TEMPLATE RENDERING (Before thread spawn)
        info_fields = {}
        for row in edit_form.query.all():
            field_data = form_data.get(row.label)
            if row.field_type == "Checkbox":
                info_fields[row.label] = (
                    " ".join(field_data) if isinstance(field_data, list) else ""
                )
            else:
                info_fields[row.label] = field_data

        event_fields = {}
        if event_obj is not None and register_for_event:
            event_fields["Ticket Type"] = form_data.get("event_tickets", "")
            for question in event_obj.questions.split("\n"):
                event_fields[question] = form_data.get(f"event_{question}", "")

        event_url = (
            url_for(
                "events.event_register",
                event_name=event_obj.name.replace(" ", "-"),
                token=token,
                _external=True,
            )
            if event_obj
            else None
        )
        update_url = url_for("update.update_info", token=token, _external=True)

        # PHASE 1.6: SETUP SESSION FOR PHONE VERIFICATION (if validation succeeded)
        if show_otp:
            session_user_data = {
                "first_name": form_data["first_name"],
                "last_name": form_data["last_name"],
                "primary_email": prim_email,
                "primary_verified": "TRUE",
                "primary_subscribed": "TRUE" if form_data["primary_subscribe"] else "FALSE",
                "secondary_email": sec_email,
                "secondary_verified": "FALSE",
                "secondary_subscribed": "TRUE" if form_data["secondary_subscribe"] else "FALSE",
                "update_url": update_url,
                "info_fields": info_fields,
            }

            session_event_data = None
            if event_obj is not None and register_for_event:
                session_event_data = {
                    "event_url": event_url,
                    "event_reg": "yes",
                    "event_name": event_obj.name,
                    "event_fields": event_fields,
                }

            session_phone_data = {
                "phone_number": phone_number,
                "phone_subscribe": "TRUE"
                if form_data.get("phone_data", {}).get("phone_subscribe", False)
                else "FALSE",
            }

            setup_otp_verification_session(
                session, session_user_data, session_event_data, session_phone_data
            )

        @copy_current_request_context
        def execute_complete_registration():
            """Refactored function using separated logic and side effects"""
            try:
                # PHASE 1: CALCULATE USER DATA (Pure Logic)
                # Generate order number and timestamp
                wks_columns = get_wks_columns(wks)
                next_order = (
                    int(wks.col_values(wks_columns["Order"])[-1]) + 1
                    if wks.col_values(wks_columns["Order"])[-1].isdigit()
                    else 1
                )
                current_timestamp = str(
                    datetime.now(tz)
                    .replace(second=0, microsecond=0)
                    .strftime("%Y-%m-%d %I:%M %p")
                )

                # Calculate user data for creation
                user_data = calculate_new_user_creation(
                    form_data, custom_fields, next_order, current_timestamp
                )

                # Calculate event data if user opted to register
                event_data = None
                if register_for_event:
                    event_questions = event_obj.questions.split("\n")
                    event_data = calculate_event_registration_from_complete(
                        form_data, event_questions, register_for_event
                    )

                # PHASE 3: EXECUTE SIDE EFFECTS
                # 3.1: Clear conflicting emails and send notifications (use the already-computed conflict_decision)
                if conflict_decision.emails_to_clear:
                    execute_cell_updates(
                        conflict_decision.emails_to_clear, "membership"
                    )

                for notification in conflict_decision.notification_emails:
                    send_deletion_notice_email(
                        notification["to"],
                        notification["user_first_name"],
                        notification["user_last_name"],
                        notification["deleted_email"],
                    )

                # 3.2: Create new user record
                user_row = create_complete_user_registration(user_data, custom_fields)

                # 3.3: Send verification email for secondary email (if provided)
                if sec_email and sec_email.strip():
                    send_verification_email(
                        sec_email,
                        form_data["first_name"],
                        form_data["last_name"],
                        start_expiry_timer=False,
                    )

                # 3.4: Create event registration if requested
                if event_data and register_for_event:
                    user_data_for_event = {
                        "first_name": form_data["first_name"],
                        "last_name": form_data["last_name"],
                        "primary_email": prim_email,
                        "secondary_email": sec_email,
                    }

                    # Extract phone data in the format expected by event registration
                    phone_data_for_event = form_data.get("event_phone_data")

                    # Use phone-aware event registration function
                    create_event_registration_with_phone(
                        event_obj.name,
                        user_data_for_event,
                        event_data,
                        phone_data_for_event,
                    )

                # 3.5: Send confirmation email (using pre-calculated data from main thread)
                send_complete_registration_confirmation_email(
                    prim_email,
                    user_data,
                    info_fields,
                    event_fields,
                    event_url,
                    update_url,
                    event_obj.name if event_obj is not None else None,
                )

                # Return success
                return {"status": "success"}

            except Exception as e:
                # Log comprehensive error details
                logger.log_background_error(
                    "/full-registration/<token>",
                    prim_email,
                    {
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "stack_trace": traceback.format_exc(),
                    },
                )
                return {"status": "error", "message": str(e)}

        # Execute the complete registration logic in BACKGROUND THREAD
        thread = Thread(target=execute_complete_registration)
        thread.start()

        # Return immediately based on phone validation result
        if show_otp:
            return redirect(url_for("confirm.otp"))
        else:
            # Render success page immediately (don't wait for thread)
            return render_template(
                "receipt.html",
                event_url=event_url,
                update_url=update_url,
                first=form.first_name.data,
                last=form.last_name.data,
                primary_email=form.primary_email.data,
                primary_verified="TRUE",
                primary_subscribed="TRUE" if form.primary_subscribe.data else "FALSE",
                secondary_email=form.secondary_email.data,
                secondary_verified="FALSE",
                secondary_subscribed="TRUE" if form.secondary_subscribe.data else "FALSE",
                phone_number=phone_number if phone_number else "",
                phone_number_verified="FALSE",
                info_fields=info_fields,
                event_name=event_obj.name if event_obj is not None else None,
                event_fields=event_fields,
            )

    else:
        # GET request - clear any stale flash messages from previous sessions
        if request.method == "GET":
            get_flashed_messages()  # Consume and discard any existing flash messages
        return render_template("complete_registration.html", form=form, token=token)
