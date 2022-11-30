from project import app
from flask import Blueprint, render_template

membership_blueprint = Blueprint("membership", __name__, template_folder="../templates/home")

@membership_blueprint.route("/membership", methods=["GET", "POST"])
def homepage(): 
    return render_template("homepage.html")