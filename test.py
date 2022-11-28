import imap_tools
import re
import bounced
import email
import bounce_email
from project import app
from datetime import date, timedelta
from validate_email import validate_email, validate_email_or_fail


is_valid = validate_email('mlupi@bdgrowers.com', smtp_debug=True)
print(is_valid)

# with imap_tools.MailBox(app.config["IMAP_SERVER"]).login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"], "Bounces") as mailbox:
#     for msg in mailbox.fetch(limit=1, mark_seen=False):
#         bounce = bounce_email.BounceEmail(msg.text)
#         print(bounce.is_bounced)
