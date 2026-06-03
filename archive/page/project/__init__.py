from flask import Flask, render_template
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from config.default import Config

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


@app.context_processor
def inject_event():
    # The events feature has been removed. Templates still reference `event`
    # in `{% if event %}` guards and `{{ event.* }}`, so expose it as None.
    return dict(event=None)


# Flask Blueprints
from project.views.home import home_blueprint

app.register_blueprint(home_blueprint)
