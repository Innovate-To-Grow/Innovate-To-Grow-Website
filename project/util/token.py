from itsdangerous import URLSafeTimedSerializer
from project import app

def generate_token(email):
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return serializer.dumps(email, salt=app.config["SECURITY_PASSWORD_SALT"])

def confirm_token(token, expiration=300): 
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
    except:
        return False

    return email


def confirm_token_no_expiry(token): 
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'])
    except:
        return False

    return email


def confirm_token_24_hours(token, expiration=86400): 
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    
    try:
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
    except:
        return False

    return email