import os

from dotenv import load_dotenv
from flask import Flask
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from config.default import Config

load_dotenv()

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


@app.context_processor
def inject_event():
    # The events feature has been removed. Templates still reference `event`
    # in `{% if event %}` guards and `{{ event.* }}`, so expose it as None.
    return dict(event=None)


@app.context_processor
def inject_sheets_api_key():
    # The event pages call the Google Sheets API client-side. Inject the key at
    # render time from the environment (.env, gitignored) so it never lives in
    # committed template source. It is still exposed to the browser — that is
    # unavoidable for a client-side key; restrict it by HTTP referrer + Sheets
    # API only in the Google Cloud console.
    return dict(sheets_api_key=os.getenv("SHEETS_API_KEY", ""))


# Flask Blueprints
from project.views import home_blueprint

app.register_blueprint(home_blueprint)
