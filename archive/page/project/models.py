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
