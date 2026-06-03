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
    first_name = db.Column("first_name", db.String())
    last_name = db.Column("last_name", db.String())
    email = db.Column("email", db.String(), unique=True)
    password = db.Column("password", db.String())
    role = db.Column("role", db.String())

    def __init__(self, first_name, last_name, email, password, role):
        self.first_name = first_name
        self.last_name = last_name
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


class event(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    name = db.Column("name", db.String())
    date = db.Column("date", db.String())
    time = db.Column("time", db.String())
    location = db.Column("location", db.String())
    description = db.Column("description", db.String())
    live = db.Column("live", db.Boolean)
    tickets = db.Column("tickets", db.String())
    questions = db.Column("questions", db.String())

    def __init__(self, name, date, time, location, description, live, tickets, questions):
        self.name = name
        self.date = date
        self.time = time
        self.location = location
        self.description = description
        self.live = live
        self.tickets = tickets
        self.questions = questions
