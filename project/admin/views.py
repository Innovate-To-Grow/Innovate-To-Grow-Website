from flask import request, flash, render_template
from flask_admin import BaseView, expose
from project import wks
from project.util.email import send_email_list
from project.admin.forms import EmailForm

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
                    if user[10] == "TRUE":
                        email_list.append(str(user[5]))
                    if user[11] == "TRUE":
                        email_list.append(str(user[6]))
            elif selection == "Verified":
                for i in range(2, wks.row_count + 1):
                    user = wks.row_values(i)
                    if user[7] == "TRUE":
                        email_list.append(str(user[5]))
                    if user[8] == "TRUE":
                        email_list.append(str(user[6]))
            
            subject = request.form.get("subject")

            body = request.form.get("body")
            body = body.replace('\n', '<br>')

            html = render_template("admin/basic_email.html", body=body)

            send_email_list(email_list, subject, html)
                
            flash("Emails sent successfully to " + str(selection) + " users.")
            

        return self.render('admin/contact.html', form=form)