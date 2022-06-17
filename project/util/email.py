from flask_mail import Message
from project import app, mail

def send_email(recipient, subject, template):
    message = Message(subject, 
                    recipients = [recipient], 
                    html = template, 
                    sender = app.config["MAIL_DEFAULT_SENDER"])
    mail.send(message)

def send_async_email(recipient_list, subject, template):
    with mail.connect() as conn:
        for recipient in recipient_list:
            message = Message(subject,
                    recipients = [recipient],
                    html = template,
                    sender = app.config["MAIL_DEFAULT_SENDER"])
        conn.send(message)