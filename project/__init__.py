import os
from os import path
from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from config.default import Config, APP_ROOT
# from project.registration.views import wks

# Google Sheet
import gspread
sa = gspread.service_account()
sh = sa.open("I2G-Master-People")
wks = sh.worksheet("double-email-test")

#Flask
app = Flask(__name__)

app.config.from_object(Config())

#Flask Mail
mail = Mail(app)

#SQLAlchemy
db = SQLAlchemy(app)
db.init_app(app)

#Login Manager
login_manager = LoginManager()
login_manager.init_app(app)

#Flask Blueprints
from project.home.views import home_blueprint
from project.registration.views import registration_blueprint
from project.update.views import update_blueprint
app.register_blueprint(home_blueprint)
app.register_blueprint(registration_blueprint)
app.register_blueprint(update_blueprint)

#Flask Admin
# from project.models import member_roster, member_data
# admin_app = Admin(app, name='Admin Page', template_mode='bootstrap3')
# admin_app.add_view(ModelView(member_roster, db.session))
# admin_app.add_view(ModelView(member_data, db.session))
# from project.admin.views import BounceView, ContactView
# admin_app.add_view(BounceView(name = 'Email Bounce', endpoint = 'bounce'))
# admin_app.add_view(ContactView(name = 'Contact', endpoint = 'contact'))

login_manager.login_view = "member_roster.login"
login_manager.login_message_category = "danger"

from project.models import member_roster

@login_manager.user_loader
def load_user(user_id):
    user = wks.find(str(user_id), in_column = 0)

    if user is not None:
        user = wks.row_values(user.row)

        user = member_roster(id = user[0],
                             first_name = user[1],
                             last_name = user[2],
                             primary_email = user[3],
                             secondary_email = user[4],
                             primary_email_status = user[5],
                             secondary_email_status = user[6],
                             info_completed = user[7],
                             primary_subscribe = user[11],
                             secondary_subscribe = user[12])
                            
    return user

