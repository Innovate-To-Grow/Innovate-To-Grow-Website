import os
from os import path
from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from config.default import Config, APP_ROOT

# Google Sheet
import gspread
wks = gspread.service_account().open("I2G-Master-People").worksheet("double-email-test")

#Flask
app = Flask(__name__)

app.config.from_object(Config())

#Flask Mail
mail = Mail(app)

#SQLAlchemy
db = SQLAlchemy(app)
db.init_app(app)

#Flask Blueprints
from project.home.views import home_blueprint
from project.registration.views import registration_blueprint
from project.update.views import update_blueprint
app.register_blueprint(home_blueprint)
app.register_blueprint(registration_blueprint)
app.register_blueprint(update_blueprint)

#Flask Admin
from project.models import dynamic_form
admin_app = Admin(app, name='Admin Page', template_mode='bootstrap3')
admin_app.add_view(ModelView(dynamic_form, db.session))
from project.admin.views import ContactView
admin_app.add_view(ContactView(name = 'Contact', endpoint = 'contact'))

if not path.exists(APP_ROOT + '/db'): os.makedirs(APP_ROOT + '/db')
if not path.exists(APP_ROOT + '/db/memberData.sqlite3'): db.create_all(app=app)