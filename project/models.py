from project import db

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
    username = db.Column("username", db.String())
    password = db.Column("password", db.String())

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False
    
    def get_id(self):
        return self.id

    def verify_password(self, password):
        u = user.query.filter(user.password == password).first()
        if u is not None:
            return True
        return False