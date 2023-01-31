from flask import request, flash, render_template, redirect, url_for
from flask_login import current_user, login_user, login_required, logout_user
from flask_admin import BaseView, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, FieldList, TextAreaField, SubmitField
from wtforms.validators import EqualTo, Email, InputRequired
from project import db, wks, sh
from project.models import edit_form, user
from project.utils.email import send_email
from project.utils.field import get_field
from project.utils.token import generate_token, confirm_token_no_expiry
from project.utils.index_helper import arr_indices
from project.forms.admin_forms import EmailForm, LoginForm, NewAdmin, RegisterAdmin
from project.forms.update_forms import NotEqualTo
from werkzeug.security import generate_password_hash


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
        email = confirm_token_no_expiry(token)
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
                    u = user(email, generate_password_hash(request.form["password"]), role_str)
                    db.session.add(u)
                    db.session.commit()
                    login_user(u)
                    flash("Administrator account created")
                    return redirect(url_for("admin.index"))
            else:
                flash("Passwords do not match")

        return self.render("admin/register_admin_form.html", form=form, role=role, token=token)


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
                register_url = url_for("admin.register_admin", role=role, token=token, _external=True)
                html = render_template("admin/new_admin_email.html", admin_url=admin_url, register_url=register_url)

                send_email(request.form["email"], subject, html)
                flash("Instructions to register as a new admin have been sent to {}".format(request.form["email"]))

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
                    submit = SubmitField('Submit')

                for row in edit_form.query.all():
                    setattr(InformationForm, row.label, get_field(row))
                form = InformationForm()

            if request.form.get("Preview Update Form"):

                class UpdateForm(FlaskForm):
                    first_name = StringField('First Name', [InputRequired(' ')])
                    last_name = StringField('Last Name', [InputRequired(' ')])
                    primary_email = StringField('Primary Email Address', [InputRequired(' '), Email()])
                    confirm_primary = StringField(
                        'Confirm Primary Email',
                        [InputRequired(' '),
                         EqualTo('primary_email', message='Must match primary email')])
                    primary_subscribe = BooleanField('Enable Email Notifications with Primary')
                    secondary_email = StringField(
                        'Secondary Email Address',
                        [InputRequired(' '),
                         Email(),
                         NotEqualTo('primary_email', message='Can not be the same email')])
                    confirm_secondary = StringField(
                        'Confirm Secondary Email',
                        [InputRequired(' '),
                         EqualTo('secondary_email', message='Must match secondary email')])
                    secondary_subscribe = BooleanField('Enable Email Notifications with Secondary')
                    submit = SubmitField('Submit')

                for row in edit_form.query.all():
                    setattr(UpdateForm, row.label, get_field(row))
                form = UpdateForm()

            return render_template("admin/preview_form.html", form=form)

    def scaffold_form(self):
        form = super(EditFormModelView, self).scaffold_form()
        form.label = StringField("Label", [InputRequired(" ")])
        form.required = BooleanField("Required?")
        form.field_type = SelectField("Field Type", choices=["Text", "Dropdown", "Checkbox"])
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
        data = {"label": model.label, "required": model.required, "field_type": model.field_type, "options": options}
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
            columns = ["First Name", "Last Name", "Email", "Ticket Type"]
            sh.worksheet(model.name).append_row(columns)

        for question in model.questions.split("\n"):
            if question not in sh.worksheet(model.name).row_values(1):
                sh.worksheet(model.name).update_cell(1, len(sh.worksheet(model.name).row_values(1)) + 1, question)

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
            "tickets": tickets,
            "questions": questions
        }
        form.process(data=data)


class ContactView(BaseView):

    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/", methods=["GET", "POST"])
    def contact(self):
        form = EmailForm(request.form)

        arr_idx = arr_indices()

        if request.method == "POST" and form.validate():
            selection = request.form.get("selection")
            email_list = []

            if selection == "Subscribed":
                for i in range(2, wks.row_count + 1):
                    user = wks.row_values(i)
                    if user[arr_idx["Primary Subscribed"]] == "TRUE":
                        email_list.append(
                            (user[arr_idx["First Name"]], user[arr_idx["Last Name"]], user[arr_idx["Primary Email"]]))
                    if user[arr_idx["Secondary Subscribed"]] == "TRUE":
                        email_list.append((user[arr_idx["First Name"]], user[arr_idx["First Name"]],
                                           user[arr_idx["Secondary Email"]]))
            elif selection == "Verified":
                for i in range(2, wks.row_count + 1):
                    user = wks.row_values(i)
                    if user[arr_idx["Primary Verified"]] == "TRUE":
                        email_list.append(
                            (user[arr_idx["First Name"]], user[arr_idx["Last Name"]], user[arr_idx["Primary Email"]]))
                    if user[arr_idx["Secondary Verified"]] == "TRUE":
                        email_list.append(
                            (user[arr_idx["First Name"]], user[arr_idx["Last Name"]], user[arr_idx["Secondary Email"]]))

            if len(email_list) == 0:
                flash("No valid emails in database")

            else:
                subject = request.form.get("subject")

                body = request.form.get("body")
                body = body.replace("\n", "<br>")

                for user in email_list:
                    html = render_template("admin/basic_email.html",
                                           first=user[arr_idx["First Name"]],
                                           last=user[arr_idx["Last Name"]],
                                           body=body)
                    send_email(user[2], subject, html)

                flash("Emails sent successfully to " + str(selection) + " users.")

        return self.render("admin/contact.html", form=form)