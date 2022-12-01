import os
import re

# Get directory
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = re.sub('config', '', APP_ROOT) + "/project"


class Config():
    SECRET_KEY = "98226"
    SECURITY_PASSWORD_SALT = "38159"
    DEBUG = False

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + APP_ROOT + "/db/data.sqlite3"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = "smtp.gmail.com"
    IMAP_SERVER = "imap.gmail.com"
    MAIL_PORT = 465
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = "i2g@g.ucmerced.edu"
    MAIL_PASSWORD = "iekmvhditchuxnik"

    MAIL_DEFAULT_SENDER = "i2g@g.ucmerced.edu"