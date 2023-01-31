import os
from os import path
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_admin import Admin
from config.default import Config, APP_ROOT
from werkzeug.security import generate_password_hash

# Google Sheet
import gspread

gc = gspread.service_account()
sh = gc.open("I2G Membership")
wks = sh.worksheet("Members")

#Flask
app = Flask(__name__)

app.config.from_object(Config())

#SQLAlchemy
db = SQLAlchemy(app)
db.init_app(app)

#Flask Blueprints
from project.views.home import home_blueprint
from project.views.registration import registration_blueprint
from project.views.update import update_blueprint
from project.views.about import about_blueprint
from project.views.events import events_blueprint
from project.views.geo import geo_blueprint

app.register_blueprint(home_blueprint)
app.register_blueprint(about_blueprint)
app.register_blueprint(registration_blueprint)
app.register_blueprint(update_blueprint)
app.register_blueprint(events_blueprint)
app.register_blueprint(geo_blueprint)

#Flask Admin
from project.models import edit_form, user, event
from project.views.admin import IndexView, UserModelView, EditFormModelView, EventModelView, ContactView

admin_app = Admin(app, name="Admin Page", index_view=IndexView(), template_mode="bootstrap3")
admin_app.add_view(UserModelView(user, db.session, name="Administrators"))
admin_app.add_view(EditFormModelView(edit_form, db.session, name="Edit Form"))
admin_app.add_view(EventModelView(event, db.session, name="Events"))
admin_app.add_view(ContactView(name="Contact", endpoint="contact"))

# Flask Login Manager
login_manager = LoginManager(app)
login_manager.session_protection = "strong"
login_manager.login_view = "admin.login"


@login_manager.user_loader
def load_user(user_id):
    return user.query.get(user_id)


if not path.exists(APP_ROOT + "/db"):
    os.makedirs(APP_ROOT + "/db")
if not path.exists(APP_ROOT + "/db/data.sqlite3"):
    db.create_all(app=app)
    u = user("admin@admin.com", generate_password_hash("admin"), "superadmin")
    db.session.add(u)
    db.session.commit()