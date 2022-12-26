import gspread, uuid
from project import app
from flask import Blueprint, render_template, request, jsonify


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

@home_blueprint.route("/event", methods=["GET", "POST"])
def event():
    return render_template("event.html")

@home_blueprint.route("/schedule", methods=["GET", "POST"])
def schedule():
    return render_template("schedule.html")

@home_blueprint.route("/projects-teams", methods=["GET", "POST"])
def projects_teams():
    return render_template("projects-teams.html")

@home_blueprint.route("/judges", methods=["GET", "POST"])
def judges():
    return render_template("judges.html")

@home_blueprint.route("/attendees", methods=["GET", "POST"])
def attendees():
    return render_template("attendees.html")

@home_blueprint.route("/student", methods=["GET", "POST"])
def students():
    return render_template("students.html")

@home_blueprint.route("/acknowledgement", methods=["GET", "POST"])
def acknowledgement():
    return render_template("acknowledgement.html")


@home_blueprint.route("/past-projects", methods=["GET", "POST"])
@home_blueprint.route("/past-projects/<uuid_string>", methods=["GET", "POST"])
def past_projects(uuid_string=None):
    wks = gspread.service_account().open("Shareable Merge Tables").worksheet("Sheet1")
    if request.method == "POST":
        data = request.get_json()
        uuid_string = str(uuid.uuid4())
        
        team_name = ""
        team_number = ""

        for d in data[:-1]:
            team_name += d["Team Name"] + " ; "
            team_number += d["Team#"] + " ; "

        team_name += data[-1]["Team Name"]
        team_number += data[-1]["Team#"]
        
        wks.append_row(values=[uuid_string, team_name, team_number])
       
        return jsonify({"uuid_string": uuid_string})

    team_names = []
    team_numbers = []

    if uuid_string is not None:
        cell = wks.find(uuid_string, in_column=1)
        if cell is not None:
            query = wks.row_values(cell.row)
            team_names = query[1].split(" ; ")
            team_numbers = query[2].split(" ; ")
    
    return render_template("past-projects.html", uuid_string=uuid_string, team_names=team_names, team_numbers=team_numbers)
