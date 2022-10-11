from project import db

class edit_form(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    field_type = db.Column("field_type", db.String())
    label = db.Column("label", db.String())
    options = db.Column("options", db.String())
    
    def __init__(self, field_type, label, options):
        self.field_type = field_type
        self.label = label
        self.options = options


class current_form(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    field_type = db.Column("field_type", db.String())
    label = db.Column("label", db.String())
    options = db.Column("options", db.String())

    def __init__(self, field_type, label, options):
        self.field_type = field_type
        self.label = label
        self.options = options


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
        if u != None:
            return True
        return False
