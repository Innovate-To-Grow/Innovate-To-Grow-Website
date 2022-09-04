from flask_mail import Message
from project import app, mail

def send_email(recipient, subject, template):
    message = Message(subject, 
                    recipients = [recipient], 
                    html = template, 
                    sender = app.config["MAIL_DEFAULT_SENDER"])
    mail.send(message)


def send_email_list(recipient_list, subject, template):
    for recipient in recipient_list:
        message = Message(subject,
                          recipients = [recipient],
                          html = template,
                          sender = app.config["MAIL_DEFAULT_SENDER"])
        mail.send(message) 