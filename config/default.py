import os
import re

# Get directory
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = re.sub('config', '', APP_ROOT) + "/project"


class Config():
    SECRET_KEY = "98226"
    SECURITY_PASSWORD_SALT = "38159"

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + APP_ROOT + "/db/data.sqlite3"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = "smtp.gmail.com"
    IMAP_SERVER = "imap.gmail.com"

    MAIL_ALIAS = "Innovate to Grow - UC Merced"
    MAIL_USERNAME = "i2g@g.ucmerced.edu"
    MAIL_PASSWORD = "iekmvhditchuxnik"

    URL_PREFIX = "/membership"

    VERIF_SUBJECT = "I2G Membership - Confirm Your Email Address"
    UPDATE_SUBJECT = "I2G membership - Link to Update Your Information"
    REMOVE_SUBJECT = "I2G Membership - Unverified Email Removed"

    TOKEN_EXPIRATION = 300
    VERIF_EXPIRATION = 60
