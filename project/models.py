from project import db

class dynamic_form(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    field_type = db.Column("field_type", db.String())
    label = db.Column("label", db.String())
    options = db.Column("options", db.String())
    