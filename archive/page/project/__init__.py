import os
from os import path

from flask import Flask, render_template
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix

from config.default import APP_ROOT, Config

# Flask
app = Flask(__name__)

app.config.from_object(Config())
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

cache = Cache(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
    default_limits=["15 per 30 seconds"],
)


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(429)
def too_many_requests(e):
    return render_template("429.html"), 429


# SQLAlchemy
db = SQLAlchemy()
db.init_app(app)

import pytz

tz = pytz.timezone("America/Los_Angeles")

# Models
from project.models import edit_form, event


@app.context_processor
def inject_event():
    return dict(
        event=event.query.filter_by(live=True).order_by(event.id.desc()).first()
    )


# Google Sheet
import gspread
from gspread.client import BackoffClient

gc = gspread.service_account(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "service_account.json"),
                             client_factory=BackoffClient)
sh = gc.open(app.config["CURRENT_SPREADSHEET"])

worksheets = []
for worksheet in sh.worksheets():
    worksheets.append(worksheet.title)

if "Members" not in worksheets:
    sh.add_worksheet("Members", 1, 100)
    row = [
        "Order",
        "First Name",
        "Last Name",
        "When Started",
        "Last Updated",
        "Primary Email",
        "Primary Verified",
        "Primary Subscribed",
        "Primary Expired",
        "Primary Bounced",
        "Secondary Email",
        "Secondary Verified",
        "Secondary Subscribed",
        "Secondary Expired",
        "Secondary Bounced",
        "Info Completed",
    ]
    sh.worksheet("Members").append_row(row)

    with app.app_context():
        for row in edit_form.query.all():
            if row.label not in sh.worksheet("Members").row_values(1):
                sh.worksheet("Members").update_cell(
                    1, len(sh.worksheet("Members").row_values(1)) + 1, row.label
                )

if "Logs" not in worksheets:
    sh.add_worksheet("Logs", 1, 100)
    row = ["Order", "Transaction", "DateTime"]
    sh.worksheet("Logs").append_row(row)

wks = sh.worksheet("Members")
logs = sh.worksheet("Logs")


def get_wks_records(wks):
    wks_records = wks.get_all_records()
    for i, row in enumerate(wks_records, start=2):
        row["Row"] = i
    return wks_records


def get_wks_columns(wks):
    header_row = wks.row_values(1)
    print(f"IN GET WKS COLUMNS FUNCTION: {type(header_row)}")
    wks_columns = {header_row[i]: i + 1 for i in range(len(header_row))}
    return wks_columns


# Flask Blueprints
from project.views.events import events_blueprint
from project.views.geo import geo_blueprint
from project.views.home import home_blueprint

app.register_blueprint(home_blueprint)
app.register_blueprint(events_blueprint)
app.register_blueprint(geo_blueprint)


if not path.exists(APP_ROOT + "/db"):
    os.makedirs(APP_ROOT + "/db")
if not path.exists(APP_ROOT + "/db/data.sqlite3"):
    with app.app_context():
        db.create_all()
