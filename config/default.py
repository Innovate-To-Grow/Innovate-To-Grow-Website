import os
import re

# Get directory
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = re.sub('config', '', APP_ROOT) + "/project"


class Config():
    SECRET_KEY = "\xa6NF\x17\x8b\xc7a\xcc\x80`\xef\x90\x13M\xcc\xe5\xa8\x05\xed\x07\n\xa5oN"
    SECURITY_PASSWORD_SALT = "\xb6\x04\x91\xf8\xcf\x02CKT\xc6G\xef\x9fq\xe0\xff\xbfu\xd4\x10q\x07\x8a"

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + APP_ROOT + "/db/data.sqlite3"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = "smtp.gmail.com"
    IMAP_SERVER = "imap.gmail.com"

    MAIL_USERNAME = "i2g@g.ucmerced.edu"
    MAIL_PASSWORD = "iekmvhditchuxnik"

    URL_PREFIX = "/membership"

    VERIF_SUBJECT = "I2G Membership - Confirm Your Email Address"
    UPDATE_SUBJECT = "I2G membership - Link to Update Your Information"
    REMOVE_SUBJECT = "I2G Membership - Unverified Email Removed"

    VERIFY_TOKEN_EXPIRATION = 300
    EVENT_TOKEN_EXPIRATION = 259200
    
    EXPIRY_TIMER = 300
