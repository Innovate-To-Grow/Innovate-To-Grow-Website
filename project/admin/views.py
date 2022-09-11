from flask import request, flash, render_template
from flask_admin import BaseView, expose
from project.util.email import send_email, send_email_list
from project.models import member_roster
from project.admin.forms import EmailForm
# Google Sheet
import gspread
wks = gspread.service_account().open("I2G-Master-People").worksheet("double-email-test")

class ContactView(BaseView):
    @expose('/',  methods=["GET", "POST"])
    def contact(self):
        form = EmailForm(request.form)
        if request.method == 'POST' and form.validate(): 
            selection = request.form.get("selection")
            email_list = []
            
            if selection == "Subscribed":
                for i in range(2, wks.row_count + 1):
                    user = wks.row_values(i)
                    if user[11] == "TRUE":
                        email_list.append(str(user[3]))
                    if user[12] == "TRUE":
                        email_list.append(str(user[4]))
            elif selection == "Verified":
                for i in range(2, wks.row_count + 1):
                    user = wks.row_values(i)
                    if user[5] == "Y":
                        email_list.append(str(user[3]))
                    if user[6] == "Y":
                        email_list.append(str(user[4]))
            
            subject = request.form.get("subject")

            body = request.form.get("body")
            body = body.replace('\n', '<br>')

            html = render_template("admin/basic_email.html", body=body)

            send_email_list(email_list, subject, html)
                
            flash("Emails sent successfully to " + str(selection) + " users.")
            

        return self.render('admin/contact.html', form=form)


# class BounceView(BaseView):
#     @expose("/", methods=["GET", "POST"])
#     def bounce(self):
#         return self.render("admin/bounce.html")
