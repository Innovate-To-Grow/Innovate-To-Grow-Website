from project import app
from flask import Blueprint, render_template

about_blueprint = Blueprint("about",
                               __name__,
                               template_folder="../templates/membership/about",
                               url_prefix=app.config["URL_PREFIX"])


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@about_blueprint.route("/", methods=["GET", "POST"])
def about_us():
    return render_template("about_us.html")