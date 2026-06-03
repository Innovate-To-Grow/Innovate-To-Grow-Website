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

    SECRET_KEY = os.getenv("SECRET_KEY")
    SECURITY_PASSWORD_SALT = os.getenv("SECURITY_PASSWORD_SALT")

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + APP_ROOT + "/db/data.sqlite3"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CACHE_TYPE = "simple"
    CACHE_DEFAULT_TIMEOUT = 300
