from flask import request, flash, render_template, redirect, url_for
from flask_login import current_user, login_user, login_required, logout_user
from flask_admin import BaseView, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from wtforms import StringField, SelectField, BooleanField, FieldList
from wtforms.validators import InputRequired
from project import db, wks
from project.models import edit_form, user
from project.util.email import send_email
from project.util.field import get_field
from project.util.token import generate_token, confirm_token_24_hours
from project.forms.admin_forms import EmailForm, LoginForm, NewAdmin, RegisterAdmin 
from project.forms.registration_forms import InformationForm
from project.forms.update_forms import UpdateForm
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
        email = confirm_token_24_hours(token)
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

    @expose ("/new_admin", methods=["GET", "POST"])
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
    edit_template = "admin/edit.html"
    create_template = "admin/create.html"
    list_template = "admin/edit_form_list.html"

    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/", methods=["GET", "POST"])
    def preview(self):
        if request.method == "POST":
            if request.form.get("Preview Info Form"):
                for row in edit_form.query.all():
                    setattr(InformationForm, row.label, get_field(row))
                form = InformationForm()

            if request.form.get("Preview Update Form"):
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
        for option in form.options.data:
            options += option + "\n" if option != form.options.data[-1] else option
        model.options = options

    def after_model_change(self, form, model, is_created):
        for row in model.query.all():
            label = wks.find(row.label, in_row=1)
            if label is None:
                wks.update_cell(1, len(wks.row_values(1)) + 1, row.label)
        
    def on_form_prefill(self, form, id):
        model = self.get_one(id)
        options = model.options.split("\n")
        data = {"label": model.label, "required": model.required, "field_type": model.field_type, "options": options}
        form.process(data=data)


class ContactView(BaseView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    @expose("/",  methods=["GET", "POST"])
    def contact(self):
        form = EmailForm(request.form)
        if request.method == "POST" and form.validate(): 
            selection = request.form.get("selection")
            email_list = []

            if selection == "Subscribed":
                for i in range(2, wks.row_count + 1):
                    user = wks.row_values(i)
                    if user[10] == "TRUE":
                        email_list.append((user[1], user[2], user[5]))
                    if user[11] == "TRUE":
                        email_list.append((user[1], user[2], user[6]))
            elif selection == "Verified":
                for i in range(2, wks.row_count + 1):
                    user = wks.row_values(i)
                    if user[7] == "TRUE":
                        email_list.append((user[1], user[2], user[5]))
                    if user[8] == "TRUE":
                        email_list.append((user[1], user[2], user[6]))
            
            if len(email_list) == 0:
                flash("No valid emails in database")

            else:
                subject = request.form.get("subject")

                body = request.form.get("body")
                body = body.replace("\n", "<br>")

                for user in email_list:
                    html = render_template("admin/basic_email.html", first=user[0], last=user[1], body=body)
                    send_email(user[2], subject, html)
                    
                flash("Emails sent successfully to " + str(selection) + " users.")
            
        return self.render("admin/contact.html", form=form)