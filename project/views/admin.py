import json
import re
import time
from enum import member
from threading import Thread, enumerate

import imap_tools
from flask import (
    copy_current_request_context,
    flash,
    redirect,
    render_template,
    render_template_string,
    request,
    url_for,
)
from flask_admin import AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from gspread.cell import Cell
from werkzeug.security import generate_password_hash
from wtforms import (
    BooleanField,
    FieldList,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import Email, EqualTo, InputRequired

from project import app, db, get_wks_columns, get_wks_records, prospects, sh, sqs, wks
from project.forms.admin_forms import (
    EmailForm,
    LoginForm,
    NewAdmin,
    ProspectForm,
    RegisterAdmin,
)
from project.forms.registration_forms import NotEqualTo
from project.models import edit_form, event, user
from project.utils.admin_helpers import get_current_datetime
from project.utils.dynamic_fields import get_field
from project.utils.email import send_email
from project.utils.token import confirm_token, generate_token
from project.utils.utils import clean_phone_number


class IndexView(AdminIndexView):
    @expose("/")
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for(".login"))
        return super(IndexView, self).index()

    @expose("/login", methods=["GET", "POST"])
    def login(self):
        form = LoginForm()
        if request.method == "POST":
            if form.validate_on_submit():
                u = user.query.filter(user.email == form.email.data).first()
                if u is not None and u.verify_password(u.password, form.password.data):
                    login_user(u)
                else:
                    flash("Invalid email or password")
            else:
                flash("Invalid email")

        if current_user.is_authenticated:
            return redirect(url_for(".index"))
        return self.render("admin/login_form.html", form=form)

    @expose("/logout")
    @login_required
    def logout(self):
        logout_user()
        return redirect(url_for(".login"))

    @expose("/register_admin/<token><role>", methods=["GET", "POST"])
    def register_admin(self, role, token):
        form = RegisterAdmin()
        role_str = "superadmin" if role == "1" else "admin"
        email = confirm_token(token, None)
        if not email:
            flash("Invalid token or link has expired")
            return redirect(url_for("admin.index"))

        if request.method == "POST":
            if form.validate_on_submit():
                u = user.query.filter(user.email == email).first()

                if u is not None:
                    flash("Administrator already registered")
                    return redirect(url_for("admin.index"))
                else:
                    u = user(
                        request.form["first_name"],
                        request.form["last_name"],
                        email,
                        generate_password_hash(request.form["password"]),
                        role_str,
                    )
                    db.session.add(u)
                    db.session.commit()
                    login_user(u)
                    flash("Administrator account created")
                    return redirect(url_for("admin.index"))
            else:
                flash("Passwords do not match")

        return self.render(
            "admin/register_admin_form.html", form=form, role=role, token=token
        )


class UserModelView(ModelView):
    column_exclude_list = ["password"]
    list_template = "admin/user_list.html"
    can_create = False
    can_edit = False

    def is_accessible(self):
        if current_user.is_authenticated and current_user.has_role("admin"):
            self.can_delete = False
        if current_user.is_authenticated and current_user.has_role("superadmin"):
            self.can_delete = True

        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/new_admin", methods=["GET", "POST"])
    def new_admin(self):
        if not current_user.has_role("superadmin"):
            flash("You do not have permission to create new admins")
            return redirect(url_for("user.index_view"))

        form = NewAdmin()

        if form.validate_on_submit():
            u = user.query.filter(user.email == form.email.data).first()
            if u is not None:
                flash("Administrator already registered")
            else:
                role = "1" if request.form["role"] == "superadmin" else "0"
                token = generate_token(request.form["email"])
                subject = "I2G - New Admin Registration"

                admin_url = url_for("admin.index", _external=True)
                register_url = url_for(
                    "admin.register_admin", role=role, token=token, _external=True
                )
                html = render_template(
                    "admin/new_admin_email.html",
                    admin_url=admin_url,
                    register_url=register_url,
                )

                send_email(request.form["email"], subject, html)
                flash(
                    "Instructions to register as a new admin have been sent to {}".format(
                        request.form["email"]
                    )
                )

        return self.render("admin/new_admin_form.html", form=form)


class EditFormModelView(ModelView):
    edit_template = "admin/edit_form_edit.html"
    create_template = "admin/edit_form_create.html"
    list_template = "admin/edit_form_list.html"

    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/", methods=["GET", "POST"])
    def preview(self):
        if request.method == "POST":
            if request.form.get("Preview Info Form"):

                class InformationForm(FlaskForm):
                    submit = SubmitField("Submit")

                for row in edit_form.query.all():
                    setattr(InformationForm, row.label, get_field(row))
                form = InformationForm()

            if request.form.get("Preview Update Form"):

                class UpdateForm(FlaskForm):
                    first_name = StringField("First Name", [InputRequired(" ")])
                    last_name = StringField("Last Name", [InputRequired(" ")])
                    primary_email = StringField(
                        "Primary Email Address", [InputRequired(" "), Email()]
                    )
                    confirm_primary = StringField(
                        "Confirm Primary Email",
                        [
                            InputRequired(" "),
                            EqualTo(
                                "primary_email", message="Must match primary email"
                            ),
                        ],
                    )
                    primary_subscribe = BooleanField("Enable Email Notifications")
                    secondary_email = StringField(
                        "Secondary Email Address",
                        [
                            InputRequired(" "),
                            Email(),
                            NotEqualTo(
                                "primary_email", message="Can not be the same email"
                            ),
                        ],
                    )
                    confirm_secondary = StringField(
                        "Confirm Secondary Email",
                        [
                            InputRequired(" "),
                            EqualTo(
                                "secondary_email", message="Must match secondary email"
                            ),
                        ],
                    )
                    secondary_subscribe = BooleanField("Enable Email Notifications")
                    submit = SubmitField("Submit")

                for row in edit_form.query.all():
                    setattr(UpdateForm, row.label, get_field(row))
                form = UpdateForm()

            return render_template("admin/preview_form.html", form=form)

    def scaffold_form(self):
        form = super(EditFormModelView, self).scaffold_form()
        form.label = StringField("Label", [InputRequired(" ")])
        form.required = BooleanField("Required?")
        form.field_type = SelectField(
            "Field Type", choices=["Text", "Dropdown", "Checkbox"]
        )
        form.options = FieldList(StringField())
        return form

    def on_model_change(self, form, model, is_created):
        options = ""
        for option in form.options.data[:-1]:
            options += option + "\n"
        options += form.options.data[-1] if len(form.options.data) > 0 else ""
        model.options = options
        db.session.commit()

    def after_model_change(self, form, model, is_created):
        for row in model.query.all():
            if row.label not in wks.row_values(1):
                wks.update_cell(1, len(wks.row_values(1)) + 1, row.label)

    def on_form_prefill(self, form, id):
        model = self.get_one(id)
        options = model.options.split("\n")
        data = {
            "label": model.label,
            "required": model.required,
            "field_type": model.field_type,
            "options": options,
        }
        form.process(data=data)


class EventModelView(ModelView):
    edit_template = "admin/event_edit.html"
    create_template = "admin/event_create.html"

    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    def scaffold_form(self):
        form = super(EventModelView, self).scaffold_form()
        form.name = StringField("Event Name", [InputRequired(" ")])
        form.date = StringField("Event Date", [InputRequired(" ")])
        form.time = StringField("Event Time", [InputRequired(" ")])
        form.location = StringField("Location", [InputRequired(" ")])
        form.description = TextAreaField("Description", [InputRequired(" ")])
        form.live = BooleanField("Live?")
        form.tickets = FieldList(StringField())
        form.questions = FieldList(StringField())
        return form

    def on_model_change(self, form, model, is_created):
        tickets = ""
        for ticket in form.tickets.data[:-1]:
            tickets += ticket + "\n"
        tickets += form.tickets.data[-1] if len(form.tickets.data) > 0 else ""
        model.tickets = tickets

        questions = ""
        for question in form.questions.data[:-1]:
            questions += question + "\n"
        questions += form.questions.data[-1] if len(form.questions.data) > 0 else ""
        model.questions = questions

        db.session.commit()

    def after_model_change(self, form, model, is_created):
        worksheets = []
        for worksheet in sh.worksheets():
            worksheets.append(worksheet.title)

        if model.name not in worksheets:
            sh.add_worksheet(model.name, 1, 30)
            columns = [
                "Order",
                "First Name",
                "Last Name",
                "When Started",
                "Last Updated",
                "Membership Primary",
                "Membership Secondary",
                "Phone Number",
                "Ticket Type",
                "Will you attend on Zoom or In-Person?",
            ]
            sh.worksheet(model.name).append_row(columns)

        for question in model.questions.split("\n"):
            if question not in sh.worksheet(model.name).row_values(1):
                sh.worksheet(model.name).update_cell(
                    1, len(sh.worksheet(model.name).row_values(1)) + 1, question
                )

    def on_form_prefill(self, form, id):
        model = self.get_one(id)
        tickets = model.tickets.split("\n")
        questions = model.questions.split("\n")
        data = {
            "name": model.name,
            "date": model.date,
            "time": model.time,
            "location": model.location,
            "description": model.description,
            "live": model.live,
            "tickets": tickets,
            "questions": questions,
        }
        form.process(data=data)


class ContactView(BaseView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/", methods=["GET", "POST"])
    def contact(self):
        form = EmailForm()

        if request.method == "POST" and form.validate_on_submit():
            recip_selection = request.form.get("recip_selection")
            email_selection = request.form.get("email_selection")

            wks_records = get_wks_records(wks)

            event_obj = (
                event.query.filter_by(live=True).order_by(event.id.desc()).first()
            )
            if event_obj is not None:
                event_records = get_wks_records(sh.worksheet(event_obj.name))

            if event_obj is None and (
                recip_selection == "Event" or recip_selection == "Non-Event Subscribed"
            ):
                flash("There is no live event right now")

            else:
                subject = request.form.get("subject")
                html_from_email = None

                with imap_tools.MailBox(app.config["IMAP_SERVER"]).login(
                    app.config["MAIL_USERNAME"],
                    app.config["MAIL_PASSWORD"],
                    "Email Blasts",
                ) as mailbox:
                    for msg in mailbox.fetch(limit=1, reverse=True, bulk=True):
                        html_from_email = msg.html

                        # for img in re.findall(r'<img[^>]+>', html_from_email):
                        #     proxy_url = re.search(r'<img src="([^"]+)"[^>]+>', img)
                        #     img_url = re.search(r'<img src="[^"]+#([^"]+)"[^>]+>', img)
                        #     html_from_email = html_from_email.replace(proxy_url.group(1), img_url.group(1))

                if html_from_email is None:
                    flash("There is no email template to send.")

                else:

                    @copy_current_request_context
                    def send_blast():
                        if recip_selection == "Admin":
                            for admin in user.query.all():
                                html = render_template_string(html_from_email)
                                send_email(admin.email, subject, html)

                        elif recip_selection == "Event":
                            for attendee in event_records:
                                member = [
                                    row
                                    for row in wks_records
                                    if row["Primary Email"]
                                    == attendee["Membership Primary"]
                                    and row["Secondary Email"]
                                    == attendee["Membership Secondary"]
                                ]
                                if member:
                                    member = member[0]
                                    html = render_template_string(html_from_email)

                                    if (
                                        email_selection == "Primary"
                                        or email_selection == "Both"
                                    ):
                                        if (
                                            member["Primary Email"] != ""
                                            and member["Primary Verified"] == "TRUE"
                                        ):
                                            send_email(
                                                member["Primary Email"], subject, html
                                            )

                                    if (
                                        email_selection == "Secondary"
                                        or email_selection == "Both"
                                    ):
                                        if (
                                            member["Secondary Email"] != ""
                                            and member["Secondary Verified"] == "TRUE"
                                        ):
                                            send_email(
                                                member["Secondary Email"], subject, html
                                            )

                                    time.sleep(0.5)

                        elif recip_selection == "Subscribed":
                            for member in wks_records:
                                html = render_template_string(html_from_email)

                                if (
                                    email_selection == "Primary"
                                    or email_selection == "Both"
                                ):
                                    if (
                                        member["Primary Email"] != ""
                                        and member["Primary Subscribed"] == "TRUE"
                                    ):
                                        send_email(
                                            member["Primary Email"], subject, html
                                        )

                                if (
                                    email_selection == "Secondary"
                                    or email_selection == "Both"
                                ):
                                    if (
                                        member["Secondary Email"] != ""
                                        and member["Secondary Subscribed"] == "TRUE"
                                    ):
                                        send_email(
                                            member["Secondary Email"], subject, html
                                        )

                                time.sleep(0.5)

                        elif recip_selection == "Non-Event Subscribed":
                            for member in wks_records:
                                if not any(
                                    member["Primary Email"]
                                    == attendee["Membership Primary"]
                                    and member["Secondary Email"]
                                    == attendee["Membership Secondary"]
                                    for attendee in event_records
                                ):
                                    html = render_template_string(html_from_email)

                                    if (
                                        email_selection == "Primary"
                                        or email_selection == "Both"
                                    ):
                                        if (
                                            member["Primary Email"] != ""
                                            and member["Primary Subscribed"] == "TRUE"
                                        ):
                                            send_email(
                                                member["Primary Email"], subject, html
                                            )

                                    if (
                                        email_selection == "Secondary"
                                        or email_selection == "Both"
                                    ):
                                        if (
                                            member["Secondary Email"] != ""
                                            and member["Secondary Subscribed"] == "TRUE"
                                        ):
                                            send_email(
                                                member["Secondary Email"], subject, html
                                            )

                                    time.sleep(0.5)

                        elif recip_selection == "Verified":
                            for member in wks_records:
                                html = render_template_string(html_from_email)

                                if (
                                    email_selection == "Primary"
                                    or email_selection == "Both"
                                ):
                                    if (
                                        member["Primary Email"] != ""
                                        and member["Primary Verified"] == "TRUE"
                                    ):
                                        send_email(
                                            member["Primary Email"], subject, html
                                        )

                                if (
                                    email_selection == "Secondary"
                                    or email_selection == "Both"
                                ):
                                    if (
                                        member["Secondary Email"] != ""
                                        and member["Secondary Verified"] == "TRUE"
                                    ):
                                        send_email(
                                            member["Secondary Email"], subject, html
                                        )

                                time.sleep(0.5)

                    Thread(target=send_blast).start()

                    flash(
                        "Emails sent successfully to "
                        + str(recip_selection)
                        + " users."
                    )

        return self.render("admin/contact.html", form=form)


class CatchBouncesView(BaseView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/", methods=["GET"])
    def catch_bounces(self):
        if not any(thread.name == "Bounce Detection" for thread in enumerate()):
            label = "Click below to start automated bounce detection process"
        else:
            label = "Automated bounce detection process is currently running"

        return self.render("admin/catch_bounces.html", label=label)

    @expose("/start", methods=["POST"])
    def start(self):
        queue_name = "BounceNotificationsQueue"
        queue_url = sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]

        @copy_current_request_context
        def detect_bounces():
            while True:
                wks_records = get_wks_records(wks)
                wks_columns = get_wks_columns(wks)

                response = sqs.receive_message(
                    QueueUrl=queue_url, MaxNumberOfMessages=10
                )

                if "Messages" in response:
                    cells = []
                    messages = response["Messages"]

                    for message in messages:
                        notification = json.loads(message["Body"])
                        bounce = json.loads(notification["Message"])
                        email = bounce["bounce"]["bouncedRecipients"][0]["emailAddress"]

                        try:
                            reason = bounce["bounce"]["bouncedRecipients"][0][
                                "diagnosticCode"
                            ]
                        except (KeyError, IndexError):
                            reason = json.dumps(bounce["bounce"])

                        for row in wks_records:
                            subject = "I2G Membership - Bounce Notification"

                            if row["Primary Email"] == email:
                                cells.append(
                                    Cell(
                                        row["Row"],
                                        wks_columns["Primary Bounced"],
                                        reason,
                                    )
                                )
                                cells.append(
                                    Cell(
                                        row["Row"],
                                        wks_columns["Primary Subscribed"],
                                        "FALSE",
                                    )
                                )

                                if (
                                    row["Secondary Email"] != ""
                                    and row["Secondary Verified"] == "TRUE"
                                    and row["Secondary Bounced"] == ""
                                ):
                                    token = generate_token(row["Secondary Email"])
                                    update_url = url_for(
                                        "update.update_info",
                                        token=token,
                                        _external=True,
                                    )
                                    html = render_template(
                                        "admin/bounce_email.html",
                                        first=row["First Name"],
                                        last=row["Last Name"],
                                        email=row["Primary Email"],
                                        update_url=update_url,
                                    )
                                    send_email(row["Secondary Email"], subject, html)

                            elif row["Secondary Email"] == email:
                                cells.append(
                                    Cell(
                                        row["Row"],
                                        wks_columns["Secondary Bounced"],
                                        reason,
                                    )
                                )
                                cells.append(
                                    Cell(
                                        row["Row"],
                                        wks_columns["Secondary Subscribed"],
                                        "FALSE",
                                    )
                                )

                                if (
                                    row["Primary Email"] != ""
                                    and row["Primary Verified"] == "TRUE"
                                    and row["Primary Bounced"] == ""
                                ):
                                    token = generate_token(row["Primary Email"])
                                    update_url = url_for(
                                        "update.update_info",
                                        token=token,
                                        _external=True,
                                    )
                                    html = render_template(
                                        "admin/bounce_email.html",
                                        first=row["First Name"],
                                        last=row["Last Name"],
                                        email=row["Secondary Email"],
                                        update_url=update_url,
                                    )
                                    send_email(row["Primary Email"], subject, html)

                        receipt_handle = message["ReceiptHandle"]
                        sqs.delete_message(
                            QueueUrl=queue_url, ReceiptHandle=receipt_handle
                        )

                    if len(cells) > 0:
                        wks.update_cells(cells)

                time.sleep(60)

        if not any(thread.name == "Bounce Detection" for thread in enumerate()):
            Thread(target=detect_bounces, daemon=True, name="Bounce Detection").start()
            flash(
                "Documented bounces will be added to the database, and emails will be sent to the user to update their information."
            )
        else:
            flash("Automated bounce detection thread is already running.")

        return redirect(url_for("catch_bounces.catch_bounces"))


class DocumentationView(BaseView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/")
    def index(self):
        return redirect(url_for(".documentation"))

    @expose("/documentation", methods=["GET"])
    def documentation(self):
        return self.render("admin/documentation.html")


class ProspectsView(BaseView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/")
    def index(self):
        return redirect(url_for(".prospects"))

    @expose("/prospects", methods=["GET", "POST"])
    def prospects(self):
        form = ProspectForm()

        if request.method == "POST":
            wks_records: list[dict] = get_wks_records(wks)
            prospect_records: list[dict] = get_wks_records(prospects)
            prospect_columns: dict = get_wks_columns(prospects)

            primary_emails = {}
            secondary_emails = {}
            phone_numbers = {}

            num_primary_emails_conflicted: int = 0
            num_secondary_emails_conflicted: int = 0
            num_phone_numbers_conflicted: int = 0

            conflicted_primary_emails: list[str] = []
            conflicted_secondary_emails: list[str] = []
            conflicted_phone_numbers: list[str] = []

            when_last_checked: str = "When last checked?"
            when_signed_up_as_member: str = "When signed up as member?"
            when_started: str = "When Started"
            collison: str = "Collision?"
            secondary_collison: str = "Secondary Collision"
            phone_collision: str = "Phone Collision"
            notes_col: str = "Notes"

            cells_to_update: list[Cell] = []

            # --- Creating dictionaries for quick search later --- #
            for row in wks_records:
                row_number: int = row["Row"]
                
                p_email = str(row.get("Primary Email", "")).strip().lower()
                if p_email:
                    primary_emails[p_email] = row_number
                
                s_email = str(row.get("Secondary Email", "")).strip().lower()
                if s_email:
                    secondary_emails[s_email] = row_number

                raw_phone = str(row.get("Phone Number", ""))
                clean_phone = clean_phone_number(raw_phone)
                if clean_phone:
                    phone_numbers[clean_phone] = row_number

            for row in prospect_records:
                # --- If a prospect is already a member, we can skip them --- #
                if row.get(when_signed_up_as_member, "") != "":
                    continue

                row_number = row["Row"]
                
                # --- Creating cell for "When last checked?" column --- #
                if when_last_checked in prospect_columns:
                    last_checked_cell = Cell(
                        row_number, prospect_columns[when_last_checked], get_current_datetime()
                    )
                    cells_to_update.append(last_checked_cell)

                email = str(row.get("Email", "")).strip().lower()
                secondary_email = str(row.get("Secondary Email (optional)", "")).strip().lower()
                phone_number = str(row.get("Phone Number (optional)", ""))
                cleaned_prospect_phone = clean_phone_number(phone_number)
                
                notes = []
                is_member = False
                member_row_idx = None

                # 1. Primary Email Check
                if email:
                    if email in primary_emails:
                        num_primary_emails_conflicted += 1
                        conflicted_primary_emails.append(email)
                        
                        member_row_idx = primary_emails[email]
                        # Access member record (row index - 2 because records start at row 2 and list is 0-indexed)
                        full_row = wks_records[member_row_idx - 2] if (member_row_idx - 2) < len(wks_records) else None
                        
                        if full_row:
                            member_start_date = full_row.get(when_started, "")
                            if not member_start_date:
                                member_start_date = "Email exists in Members as a primary, but no value in When Started"

                            if when_signed_up_as_member in prospect_columns:
                                cells_to_update.append(Cell(
                                    row_number,
                                    prospect_columns[when_signed_up_as_member],
                                    member_start_date,
                                ))
                            
                            notes.append(f"Primary email found as Primary Email in Members (Row {member_row_idx}).")
                            is_member = True

                        if collison in prospect_columns:
                            cells_to_update.append(Cell(row_number, prospect_columns[collison], "TRUE"))

                    elif email in secondary_emails:
                        num_primary_emails_conflicted += 1
                        conflicted_primary_emails.append(email)
                        
                        member_row_idx = secondary_emails[email]
                        full_row = wks_records[member_row_idx - 2] if (member_row_idx - 2) < len(wks_records) else None
                        
                        if full_row:
                            member_start_date = full_row.get(when_started, "")
                            if not member_start_date:
                                member_start_date = "Email exists in Members as a secondary, but no value in When Started"

                            if when_signed_up_as_member in prospect_columns:
                                cells_to_update.append(Cell(
                                    row_number,
                                    prospect_columns[when_signed_up_as_member],
                                    member_start_date,
                                ))
                            
                            notes.append(f"Primary email found as Secondary Email in Members (Row {member_row_idx}).")
                            is_member = True

                        if collison in prospect_columns:
                            cells_to_update.append(Cell(row_number, prospect_columns[collison], "TRUE"))

                # 2. Secondary Email Check
                if secondary_email:
                    # Check against Primary Emails in Members
                    if secondary_email in primary_emails:
                        match_row_idx = primary_emails[secondary_email]
                        if match_row_idx != member_row_idx:
                            num_secondary_emails_conflicted += 1
                            conflicted_secondary_emails.append(secondary_email)
                            if secondary_collison in prospect_columns:
                                cells_to_update.append(Cell(
                                    row_number, prospect_columns[secondary_collison], "TRUE"
                                ))
                            notes.append(f"Secondary email found as Primary Email in Members (Row {match_row_idx}).")

                    # Check against Secondary Emails in Members
                    if secondary_email in secondary_emails:
                        match_row_idx = secondary_emails[secondary_email]
                        if match_row_idx != member_row_idx:
                            num_secondary_emails_conflicted += 1
                            conflicted_secondary_emails.append(secondary_email)
                            if secondary_collison in prospect_columns:
                                cells_to_update.append(Cell(
                                    row_number, prospect_columns[secondary_collison], "TRUE"
                                ))
                            notes.append(f"Secondary email found as Secondary Email in Members (Row {match_row_idx}).")

                # 3. Phone Check
                if cleaned_prospect_phone and cleaned_prospect_phone in phone_numbers:
                    match_row_idx = phone_numbers[cleaned_prospect_phone]
                    if match_row_idx != member_row_idx:
                        num_phone_numbers_conflicted += 1
                        conflicted_phone_numbers.append(phone_number)
                        if phone_collision in prospect_columns:
                            cells_to_update.append(Cell(
                                row_number, prospect_columns[phone_collision], "TRUE"
                            ))
                        notes.append(f"Phone number found in Members (Row {match_row_idx}).")

                # Update Notes
                if notes and notes_col in prospect_columns:
                    # If existing notes exist, append? For now overwrite or append to empty string in logic
                    # We'll just overwrite with new findings as this is a "check" operation
                    cells_to_update.append(Cell(row_number, prospect_columns[notes_col], " ".join(notes)))

            if cells_to_update:
                prospects.update_cells(cells_to_update)

            flash(
                f"Found conflicts - Primary: {num_primary_emails_conflicted}, Secondary: {num_secondary_emails_conflicted}, Phone: {num_phone_numbers_conflicted}"
            )
            print(
                f"Conflicts:\nPrimary Emails: {conflicted_primary_emails}\nSecondary Emails: {conflicted_secondary_emails}\nPhone Numbers: {conflicted_phone_numbers}"
            )

        return self.render("admin/prospects.html", form=form)
