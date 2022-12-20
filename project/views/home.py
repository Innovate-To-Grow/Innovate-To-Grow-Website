from project import app
from flask import Blueprint, render_template

home_blueprint = Blueprint("home", __name__, template_folder="../templates/home")


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@home_blueprint.route("/", methods=["GET", "POST"])
def mainpage():
    return render_template("index.html")


@home_blueprint.route("/about", methods=["GET", "POST"])
def about():
    return render_template("about.html")

@home_blueprint.route("/engineering-capstone", methods=["GET", "POST"])
def engineering_capstone():
    return render_template("engineering-capstone.html")

@home_blueprint.route("/about_EngSL", methods=["GET", "POST"])
def about_EngSL():
    return render_template("about_EngSL.html")

@home_blueprint.route("/software-capstone", methods=["GET", "POST"])
def software_capstone():
    return render_template("software-capstone.html")