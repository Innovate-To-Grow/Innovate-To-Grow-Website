import os
import re
from dotenv import load_dotenv
load_dotenv()

# Get directory
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = re.sub('config', '', APP_ROOT) + "/project"


class Config():
    CURRENT_SPREADSHEET = os.getenv("CURRENT_SPREADSHEET", "Test I2G Membership")

    VERIFY_TOKEN_EXPIRATION = 600
    EVENT_TOKEN_EXPIRATION = 302400
    
    EXPIRY_TIMER = 172800

    URL_PREFIX = "/membership"

    VERIF_SUBJECT = "I2G Membership - Confirm Your Email Address"
    UPDATE_SUBJECT = "I2G membership - Link to Update Your Information"
    REMOVE_SUBJECT = "I2G Membership - Unverified Email Removed"

    MAIL_SERVER = "smtp.gmail.com"
    IMAP_SERVER = "imap.gmail.com"

    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    SECRET_KEY = os.getenv("SECRET_KEY")
    SECURITY_PASSWORD_SALT = os.getenv("SECURITY_PASSWORD_SALT")

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + APP_ROOT + "/db/data.sqlite3"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CACHE_TYPE = "simple"
    CACHE_DEFAULT_TIMEOUT = 300

    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
    VERIFY_SID = os.getenv("VERIFY_SID")