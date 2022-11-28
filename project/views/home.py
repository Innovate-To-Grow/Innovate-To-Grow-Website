from project import app
from flask import Blueprint, render_template

home_blueprint = Blueprint("home", __name__, template_folder="../templates/home")

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@home_blueprint.route("/", methods=["GET", "POST"])
def mainpage(): 
    return render_template("homepage.html")