import imap_tools, re, time
from datetime import date, timedelta
from flask import render_template
from flask_mail import Message
from project import app, mail, wks

def send_email(recipient, subject, template):
    message = Message(subject, 
                    recipients = [recipient], 
                    html = template, 
                    sender = app.config["MAIL_DEFAULT_SENDER"])
    mail.send(message)


def delete_email(row, col, email):
    with app.app_context():
        time.sleep(30)
        user = wks.find(email, in_column=col)
        user = wks.row_values(user.row)
        if user[col+1] == "TRUE":
            return
        else:
            wks.update_cell(row, col, "")

            subject = "I2G - Unverified Email Removed"
            html = render_template("deleting_email.html", first=user[1], last=user[2], email=email)

            if col == 6 and user[8] == "TRUE" and user[6] != "":
                send_email(user[6], subject, html)
            if col == 7 and user[7] == "TRUE" and user[5] != "":
                send_email(user[5], subject, html)


def detect_bounce(interval):
    while True:
        time.sleep(interval)
        with imap_tools.MailBox(app.config["IMAP_SERVER"]).login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"], "Inbox") as mailbox:
            if not mailbox.folder.exists("Bounces"):
                mailbox.folder.create("Bounces")

            bounces = set()
            query = imap_tools.A(date.today() - timedelta(days=1))

            for msg in mailbox.fetch(bulk=True, mark_seen=False):
                headers = msg.headers
                if 'return-path' in headers and headers['return-path'][0] == '<>':
                    body = msg.text
                    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', body)
                    bounces.update(emails)
                    mailbox.move(msg.uid, "Bounces")
                
            for email in bounces:
                user = wks.find(email, in_column=6)
                if user is not None:
                    user_row = user.row
                    user_col = user.col
                    user = wks.row_values(user.row)
                if user is None:
                    user = wks.find(email, in_column=7)
                    if user is not None:
                        user_row = user.row
                        user_col = user.col
                        user = wks.row_values(user.row)
                    else:
                        continue

                if user_col == 6:
                    wks.update_cell(user_row, 13, "BOUNCE")
                elif user_col == 7:
                    wks.update_cell(user_row, 14, "BOUNCE")