from flask import request, flash, render_template, redirect, url_for
from flask_login import current_user, login_user, login_required, logout_user
from flask_admin import BaseView, AdminIndexView, expose, helpers
from flask_admin.contrib.sqla import ModelView
from wtforms import StringField, SelectField, FieldList, BooleanField
from wtforms.validators import InputRequired
from project import wks
from project.models import user
from project.util.email import send_email
from project.admin.forms import EmailForm, LoginForm

class IndexView(AdminIndexView):
    @expose("/")
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for(".login"))
        return super(IndexView, self).index()

    @expose("/login", methods=["GET", "POST"])
    def login(self):
        form = LoginForm(request.form)
        if helpers.validate_form_on_submit(form):
            u = user.query.filter(user.username == form.username.data).first()
            if u is not None and u.verify_password(form.password.data):
                login_user(u)
            else:
                flash("Invalid username or password")
        if current_user.is_authenticated:
            return redirect(url_for(".index"))
        return self.render("admin/login.html", form=form)

    @expose("/logout")
    @login_required
    def logout(self):
        logout_user()
        return redirect(url_for(".login"))


class UserModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    
class EditFormModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login", next=request.url))

    def scaffold_form(self):
        form = super(EditFormModelView, self).scaffold_form()
        form.label = StringField("Label", [InputRequired(' ')])
        form.field_type = SelectField("Field Type", choices=["Text", "Dropdown", "Checkbox"])
        form.options = StringField()
        form.required = BooleanField("Required?")
        return form

    def on_model_change(self, form, model, is_created):
        for row in model.query.all():
            label = wks.find(row.label, in_row=1)
            if label is None:
                wks.update_cell(1, len(wks.row_values(1)) + 1, row.label)


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