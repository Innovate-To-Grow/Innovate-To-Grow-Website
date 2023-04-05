from imap_tools import MailBox, AND
from config.default import Config


# read inbox, then get unread messages
with MailBox('imap.gmail.com').login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD, initial_folder='INBOX') as mailbox:
    unread_msgs = mailbox.fetch(AND(seen=False))
    for msg in unread_msgs:
        print(msg.html)


