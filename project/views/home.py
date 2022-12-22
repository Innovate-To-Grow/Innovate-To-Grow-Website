import uuid, gspread, time
from gspread.cell import Cell
from project import app
from project.utils.token import generate_token
from flask import Blueprint, render_template, request


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

import sys
@home_blueprint.route("/past-projects", methods=["GET", "POST"])
@home_blueprint.route("/past-projects/<uuid_string>", methods=["GET", "POST"])
def past_projects(uuid_string=None):
    test = "cum"
    uuid_string = str(uuid.uuid4())
    wks = gspread.service_account().open("Shareable Merge Tables").worksheet("Sheet1")
    if request.method == "POST":
        # get json data
        data = request.get_json()
        
        team_name = ""
        team_number = ""
        for d in data:
            # add to team name if not last d in data

            team_name += d["Team Name"] + " ; " if d != data[-1] else d["Team Name"]
            team_number += d["Team#"] + " ; " if d != data[-1] else d["Team#"]
        
        wks.append_row(values=[uuid_string, team_name, team_number])

        return render_template("past-projects.html", uuid_string=uuid_string)
    
    time.sleep(2)
    print("uuid_string: " + str(request.args.get("uuid_string")), file=sys.stderr)

    if request.args.get("uuid_string") is not None:
        cell = wks.find(request.args.get("uuid_string"))
        test = wks.row_values(cell.row)[0]

    return render_template("past-projects.html", uuid_string=test)
