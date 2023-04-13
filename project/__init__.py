import os
from os import path
from flask import Flask, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_admin import Admin
from config.default import Config, APP_ROOT
from werkzeug.security import generate_password_hash


# Flask
app = Flask(__name__)

app.config.from_object(Config())


# limiter = Limiter(
#     get_remote_address,
#     app=app,
#     default_limits=["15 per 30 seconds"]
# )


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(429)
def too_many_requests(e):
    return render_template("429.html"), 429


# SQLAlchemy
db = SQLAlchemy()
db.init_app(app)


import boto3

aws_access_key_id = "***REMOVED_AWS_KEY_ID***"
aws_secret_access_key = "***REMOVED_AWS_SECRET***"

ses = boto3.client('ses',
                   region_name='us-west-2',
                   aws_access_key_id=aws_access_key_id,
                   aws_secret_access_key=aws_secret_access_key)

sqs = boto3.client('sqs',
                   region_name='us-west-2',
                   aws_access_key_id=aws_access_key_id,
                   aws_secret_access_key=aws_secret_access_key)


import pytz
tz = pytz.timezone("America/Los_Angeles")


# Models
from project.models import user, edit_form, event

@app.context_processor
def inject_event():
    return dict(event=event.query.filter_by(live=True).order_by(event.id.desc()).first())


# Google Sheet
import gspread
from gspread.client import BackoffClient

gc = gspread.service_account(client_factory=BackoffClient)
sh = gc.open("I2G Membership")

worksheets = []
for worksheet in sh.worksheets():
    worksheets.append(worksheet.title)

if "Members" not in worksheets:
    sh.add_worksheet("Members", 1, 100)
    row = [
        "Order", "First Name", "Last Name", "When Started", "Last Updated", "Primary Email", "Primary Verified",
        "Primary Subscribed", "Primary Expired", "Primary Bounced", "Secondary Email", "Secondary Verified",
        "Secondary Subscribed", "Secondary Expired", "Secondary Bounced", "Info Completed"
    ]
    sh.worksheet("Members").append_row(row)

    with app.app_context():
        for row in edit_form.query.all():
            if row.label not in sh.worksheet("Members").row_values(1):
                sh.worksheet("Members").update_cell(1, len(sh.worksheet("Members").row_values(1)) + 1, row.label)

if "Logs" not in worksheets:
    sh.add_worksheet("Logs", 1, 100)
    row = [
        "Order", "Transaction", "DateTime"
    ]
    sh.worksheet("Logs").append_row(row)

wks = sh.worksheet("Members")
logs = sh.worksheet("Logs")

def get_wks_records(wks):
    wks_records = wks.get_all_records()
    for i, row in enumerate(wks_records, start=2):
        row['Row'] = i
    return wks_records


def get_wks_columns(wks):
    header_row = wks.row_values(1)
    wks_columns = {header_row[i]: i+1 for i in range(len(header_row))}
    return wks_columns


# Flask Blueprints
from project.views.home import home_blueprint
from project.views.registration import registration_blueprint
from project.views.update import update_blueprint
from project.views.events import events_blueprint
from project.views.geo import geo_blueprint

app.register_blueprint(home_blueprint)
app.register_blueprint(registration_blueprint)
app.register_blueprint(update_blueprint)
app.register_blueprint(events_blueprint)
app.register_blueprint(geo_blueprint)


# Flask Admin
from project.views.admin import IndexView, UserModelView, EditFormModelView, EventModelView, ContactView, CatchBouncesView

admin_app = Admin(app, name="Admin Page", index_view=IndexView(), template_mode="bootstrap3")
admin_app.add_view(UserModelView(user, db.session, name="Administrators"))
admin_app.add_view(EditFormModelView(edit_form, db.session, name="Edit Form"))
admin_app.add_view(EventModelView(event, db.session, name="Events"))
admin_app.add_view(ContactView(name="Contact", endpoint="contact"))
admin_app.add_view(CatchBouncesView(name="Catch Bounces", endpoint="catch_bounces"))


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
    with app.app_context():
        db.create_all()
        u = user("Admin", "Admin", "admin@admin.com", generate_password_hash("admin"), "superadmin")
        db.session.add(u)
        db.session.commit()
