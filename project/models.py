from project import db
from werkzeug.security import check_password_hash

class edit_form(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    label = db.Column("label", db.String())
    required = db.Column("required", db.Boolean)
    field_type = db.Column("field_type", db.String())
    options = db.Column("options", db.String())
    
    def __init__(self, label, required, options, field_type):
        self.label = label
        self.required = required
        self.options = options
        self.field_type = field_type


class user(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    email = db.Column("email", db.String(), unique=True)
    password = db.Column("password", db.String())
    role = db.Column("role", db.String())

    def __init__(self, email, password, role):
        self.email = email
        self.password = password
        self.role = role

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False
    
    def get_id(self):
        return self.id

    def verify_password(self, db_password, input_password):
        return check_password_hash(db_password, input_password)

    def has_role(self, role):
        return self.role == role
        