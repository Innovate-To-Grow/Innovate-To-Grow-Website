from flask import request, flash, render_template
from flask_admin import  BaseView, expose
from project import wks, db
from project.util.email import send_email
from project.admin.forms import EmailForm
from project.models import edit_form, current_form
from sqlalchemy import delete
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
                    full_name = user[1] + " " + user[2]
                    if user[10] == "TRUE":
                        email_list.append((full_name, user[5]))
                    if user[11] == "TRUE":
                        email_list.append((full_name, user[6]))
            elif selection == "Verified":
                for i in range(2, wks.row_count + 1):
                    user = wks.row_values(i)
                    full_name = user[1] + " " + user[2]
                    if user[7] == "TRUE":
                        email_list.append((full_name, user[5]))
                    if user[8] == "TRUE":
                        email_list.append((full_name, user[6]))
            
            subject = request.form.get("subject")

            body = request.form.get("body")
            body = body.replace('\n', '<br>')

            for user in email_list:
                html = render_template("admin/basic_email.html", name=user[0], body=body)
                send_email(user[1], subject, html)
                
            flash("Emails sent successfully to " + str(selection) + " users.")
            
        return self.render('admin/contact.html', form=form)

class SubmitView(BaseView):
    @expose('/',  methods=["GET", "POST"])
    def submit(self):
        
        db.session.query(current_form).delete()
        db.session.commit()
        
        for row in edit_form.query.all():
            data = current_form(field_type=row.field_type,label=row.label,options=row.options)
            db.session.add(data)
        db.session.commit()

        count = 16
        for row in edit_form.query.all():
            wks.update_cell(1, count, row.label)
            count += 1

        return self.render('admin/confirmed.html')