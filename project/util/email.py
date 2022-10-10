import time
from flask import render_template
from flask_mail import Message
from project import app, mail, wks

def send_email(recipient, subject, template):
    message = Message(subject, 
                    recipients = [recipient], 
                    html = template, 
                    sender = app.config["MAIL_DEFAULT_SENDER"])
    mail.send(message)


def delete_email(value, row, col, email):
    with app.app_context():
        time.sleep(value)
        user = wks.find(email, in_column=col)
        user = wks.row_values(user.row)
        if user[col+1] == "TRUE":
            return
        else:
            wks.update_cell(row,col,"")

            subject = "i2G - Unverified Email Removed"
            html = render_template("deleting_email.html", first=user[1], last=user[2], email=email)

            if col == 6 and user[8] == "TRUE" and user[6] is not "":
                send_email(user[6], subject, html)
            if col == 7 and user[7] == "TRUE" and user[5] is not "":
                send_email(user[5], subject, html)