#save token in db to prevent:
#-tokens remain valid after use (replay)
#-old tokens remain valid after new ones are issued

from itsdangerous import URLSafeTimedSerializer
from project import app

def generate_token(email):
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return serializer.dumps(email, salt=app.config["SECURITY_PASSWORD_SALT"])


def confirm_token(token, expiration): 
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
    except:
        return False

    return email.lower()
