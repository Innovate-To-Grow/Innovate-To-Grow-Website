from flask import request, flash, render_template
from flask_admin import BaseView, expose
from project.util.email import send_async_email
from project.models import member_roster
from project.admin.forms import EmailForm

class ContactView(BaseView):
    @expose('/',  methods=["GET", "POST"])
    def contact(self):
        form = EmailForm(request.form)
        if(request.method == 'POST' and form.validate()):

            verified_users = member_roster.query.filter((member_roster.primary_email_status == True) | (member_roster.secondary_email_status == True)).all()

            email_list = []

            for user in verified_users:
                if(user.primary_email_status == True):
                    email_list.append(str(user.primary_email))
                
                if(user.secondary_email_status == True):
                    email_list.append(str(user.secondary_email))

            subject = request.form.get("subject")

            body = request.form.get("body")
            body = body.replace('\n', '<br>')

            html = render_template("admin/basic_email.html", body=body)

            send_async_email(email_list, subject, html)

            flash("Emails sent successfully to verified users!")

        return self.render('admin/contact.html', form=form)


# class BounceView(BaseView):
#     @expose("/", methods=["GET", "POST"])
#     def bounce(self):
#         return self.render("admin/bounce.html")
