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

