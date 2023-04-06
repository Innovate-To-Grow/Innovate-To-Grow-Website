import imap_tools, re, time, yagmail
from datetime import date, timedelta
from project import app, ses

def send_email(recipient, subject, template):
    ses.send_email(
    Destination={
        'ToAddresses': [
            recipient,
        ],
    },
    Message={
        'Body': {
            'Html': {
                'Charset': 'UTF-8',
                'Data': template,
            },
        },
        'Subject': {
            'Charset': 'UTF-8',
            'Data': subject,
        },
    },
    Source="Innovate to Grow - University of California Merced <i2g@g.ucmerced.edu>",)
