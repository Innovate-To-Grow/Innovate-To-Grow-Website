from flask import Blueprint, render_template

home_blueprint = Blueprint("home", __name__, template_folder='templates',static_folder='static')

@home_blueprint.route("/", methods=["GET", "POST"])
def mainpage(): 
    return render_template("homepage.html")
