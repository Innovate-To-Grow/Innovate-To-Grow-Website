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


class event(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    name = db.Column("name", db.String())
    description = db.Column("description", db.String())
    date = db.Column("date", db.String())
    time = db.Column("time", db.String())
    location = db.Column("location", db.String())
    tickets = db.Column("tickets", db.String())
    questions = db.Column("questions", db.String())

    def __init__(self, name, description, date, time, location, tickets, questions):
        self.name = name
        self.description = description
        self.date = date
        self.time = time
        self.location = location
        self.tickets = tickets
        self.questions = questions


class areas(db.Model):
    __tablename__ = "areas"

    area_id = db.Column("area_id", db.Integer, primary_key=True)
    latitude1 = db.Column("latitude1", db.Float)
    longitude1 = db.Column("longitude1", db.Float)
    latitude2 = db.Column("latitude2", db.Float)
    longitude2 = db.Column("longitude2", db.Float)
    composite_id = db.Column("composite_id", db.Integer, db.ForeignKey("composites.composite_id"))

    def __init__(self, latitude1, longitude1, latitude2, longitude2, composite_id):
        self.latitude1 = latitude1
        self.longitude1 = longitude1
        self.latitude2 = latitude2
        self.longitude2 = longitude2
        self.composite_id = composite_id


class composites(db.Model):
    __tablename__ = "composites"

    composite_id = db.Column("composite_id", db.Integer, primary_key=True)
    composite_name = db.Column("composite_name", db.String())
    user_id = db.Column("user_id", db.Integer)

    def __init__(self, composite_name, user_id):
        self.composite_name = composite_name
        self.user_id = user_id


class businesses(db.Model):
    __tablename__ = "businesses"

    business_id = db.Column("business_id", db.Integer, primary_key=True)
    name = db.Column("name", db.String())
    address = db.Column("address", db.String())
    city = db.Column("city", db.String())
    postal_code = db.Column("postal_code", db.Integer)
    latitude = db.Column("latitude", db.Float)
    longitude = db.Column("longitude", db.Float)

    def __init__(self, name, address, city, postal_code, latitude, longitude):
        self.name = name
        self.address = address
        self.city = city
        self.postal_code = postal_code
        self.latitude = latitude
        self.longitude = longitude
