import os
from os import path
from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from config.default import Config, APP_ROOT

# Google Sheet
import gspread
wks = gspread.service_account().open("I2G-Master-People").worksheet("double-email-test")

form_row = wks.row_values(1)
form_size = len(form_row)
data = []
for x in range(12, form_size):
    data.append(form_row[x])

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
from project.models import edit_form, current_form, user
from project.admin.views import IndexView, UserModelView, EditFormModelView, CurrentFormModelView, ContactView, SubmitView
admin_app = Admin(app, name='Admin Page', index_view=IndexView(), template_mode='bootstrap3')
admin_app.add_view(UserModelView(user, db.session, name = "Login Info"))
admin_app.add_view(EditFormModelView(edit_form, db.session, name = "Edit Form"))
admin_app.add_view(CurrentFormModelView(current_form, db.session, name = "Current Form"))
admin_app.add_view(ContactView(name = 'Contact', endpoint = 'contact'))
admin_app.add_view(SubmitView(name = 'OVERWRITE FORM', endpoint = 'submit'))

# Flask Login Manager
login_manager = LoginManager(app)
login_manager.session_protection = 'strong'
login_manager.login_view = 'admin.login'

@login_manager.user_loader
def load_user(user_id):
    return user.query.get(user_id)

if not path.exists(APP_ROOT + '/db'): os.makedirs(APP_ROOT + '/db')
if not path.exists(APP_ROOT + '/db/memberData.sqlite3'): 
    db.create_all(app=app)

    for x in data:
        form_edit = edit_form(field_type='text', label=x, options='', required=False)
        db.session.add(form_edit)
    db.session.commit()
    
