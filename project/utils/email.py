import imap_tools, re, time, yagmail
from datetime import date, timedelta
from project import app, wks

def send_email(recipient, subject, template):
    with app.app_context():
        yag = yagmail.SMTP({app.config["MAIL_USERNAME"] : app.config["MAIL_ALIAS"]}, app.config["MAIL_PASSWORD"])
        yag.send(recipient, subject, template.replace("\n", ""))


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