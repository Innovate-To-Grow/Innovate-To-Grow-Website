import os
import gspread, uuid
from threading import Thread
from flask import Blueprint, render_template, request, jsonify
from gspread.exceptions import APIError
from project import cache

CURRENT_PROJECTS_SPREADSHEET_ID = "1KRFQ7UX35du1VJCNs4naykynTtLAr0rgtKrNOEWMkgI"
CURRENT_PROJECTS_WORKSHEET_GID = 1913722874
SERVICE_ACCOUNT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "service_account.json",
)


def _normalize_sheet_header(value):
    return "".join(character.lower() for character in value if character.isalnum())


def _build_current_projects_payload(rows):
    if not rows:
        return []

    headers = rows[0]
    normalized_headers = {
        _normalize_sheet_header(header): index for index, header in enumerate(headers)
    }
    fallback_indices = {
        "Track": 0,
        "Order": 1,
        "Year-Semester": 2,
        "Class": 3,
        "Team#": 4,
        "TeamName": 5,
        "Project Title": 6,
        "Organization": 7,
        "Industry": 8,
        "Abstract": 9,
        "Student Names": 10,
        "NameTitle": 11,
    }
    field_aliases = {
        "Track": ["Track"],
        "Order": ["Order"],
        "Year-Semester": ["Year-Semester", "Year Semester", "Semester"],
        "Class": ["Class"],
        "Team#": ["Team#", "Team Number", "Team"],
        "TeamName": ["TeamName", "Team Name"],
        "Project Title": ["Project Title", "Title"],
        "Organization": ["Organization", "Partner Organization", "Partner"],
        "Industry": ["Industry"],
        "Abstract": ["Abstract", "Project Abstract"],
        "Student Names": ["Student Names", "Students"],
        "NameTitle": ["NameTitle", "Name Title", "Contact Name Title"],
    }

    def get_cell(row, field_name):
        for alias in field_aliases[field_name]:
            alias_index = normalized_headers.get(_normalize_sheet_header(alias))
            if alias_index is not None and alias_index < len(row):
                return row[alias_index]

        fallback_index = fallback_indices[field_name]
        if fallback_index < len(row):
            return row[fallback_index]
        return ""

    projects = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue

        project = {
            field_name: get_cell(row, field_name) for field_name in field_aliases
        }
        if project["Team#"] or project["Project Title"] or project["TeamName"]:
            projects.append(project)

    return projects

home_blueprint = Blueprint("home", __name__, template_folder="../templates/home")


@home_blueprint.route("/", methods=["GET", "POST"])
@cache.cached()
def mainpage():
    return render_template("home-pre-event.html")
    # return render_template("event.html")
    # return render_template("home-during-event.html")
    # return render_template("home-post-event.html")
    # return render_template("home-during-semester.html")


@home_blueprint.route("/about", methods=["GET", "POST"])
@cache.cached()
def about():
    return render_template("about.html")


@home_blueprint.route("/privacy", methods=["GET", "POST"])
@cache.cached()
def text_toc():
    return render_template("terms_and_conditions.html")


@home_blueprint.route("/engineering-capstone", methods=["GET", "POST"])
@cache.cached()
def engineering_capstone():
    return render_template("engineering-capstone.html")


@home_blueprint.route("/about_EngSL", methods=["GET", "POST"])
@cache.cached()
def about_EngSL():
    return render_template("about_EngSL.html")


@home_blueprint.route("/software-capstone", methods=["GET", "POST"])
@cache.cached()
def software_capstone():
    return render_template("software-capstone.html")


@home_blueprint.route("/event", methods=["GET", "POST"])
@cache.cached()
def event():
    return render_template("event.html")


@home_blueprint.route("/schedule", methods=["GET", "POST"])
@cache.cached()
def schedule():
    return render_template("schedule.html")


@home_blueprint.route("/projects-teams", methods=["GET", "POST"])
@cache.cached()
def projects_teams():
    return render_template("projects-teams.html")


@home_blueprint.route("/judges", methods=["GET", "POST"])
@cache.cached()
def judges():
    return render_template("judges.html")


@home_blueprint.route("/attendees", methods=["GET", "POST"])
@cache.cached()
def attendees():
    return render_template("attendees.html")


@home_blueprint.route("/students", methods=["GET", "POST"])
@cache.cached()
def students():
    return render_template("students.html")


@home_blueprint.route("/acknowledgement", methods=["GET", "POST"])
@cache.cached()
def acknowledgement():
    return render_template("acknowledgement.html")


@home_blueprint.route("/past-events", methods=["GET", "POST"])
@cache.cached()
def past_events():
    return render_template("past-events.html")


@home_blueprint.route("/projects", methods=["GET", "POST"])
@cache.cached()
def projects():
    return render_template("projects.html")


@home_blueprint.route("/current-projects", methods=["GET", "POST"])
@cache.cached()
def current_projects():
    return render_template("current-projects.html")


@home_blueprint.route("/api/current-projects", methods=["GET"])
def current_projects_data():
    try:
        spreadsheet = gspread.service_account(filename=SERVICE_ACCOUNT_PATH).open_by_key(
            CURRENT_PROJECTS_SPREADSHEET_ID
        )
        worksheet = next(
            (
                sheet
                for sheet in spreadsheet.worksheets()
                if sheet.id == CURRENT_PROJECTS_WORKSHEET_GID
            ),
            None,
        )

        if worksheet is None:
            return jsonify({"error": "Current projects worksheet not found."}), 404

        rows = worksheet.get("A:Y")
        return jsonify(_build_current_projects_payload(rows))
    except APIError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        if status_code == 403:
            return (
                jsonify(
                    {
                        "error": "Google Sheet permission denied for the current-projects service account."
                    }
                ),
                403,
            )
        return jsonify({"error": f"Unable to load current projects data: {exc}"}), 502
    except Exception as exc:
        return (
            jsonify({"error": f"Unable to load current projects data: {exc}"}),
            502,
        )


@home_blueprint.route("/project-submission", methods=["GET", "POST"])
@cache.cached()
def project_submission():
    return render_template("project-submission.html")


@home_blueprint.route("/sample-proposals", methods=["GET", "POST"])
@cache.cached()
def sample_proposals():
    return render_template("sample-proposals.html")


@home_blueprint.route("/partnership", methods=["GET", "POST"])
@cache.cached()
def partnership():
    return render_template("partnership.html")


@home_blueprint.route("/sponsorship", methods=["GET", "POST"])
@cache.cached()
def sponsorship():
    return render_template("sponsorship.html")


@home_blueprint.route("/FAQs", methods=["GET", "POST"])
@cache.cached()
def faq():
    return render_template("faq.html")


@home_blueprint.route("/I2G-student-agreement", methods=["GET", "POST"])
@cache.cached()
def I2G_student_agreement():
    return render_template("I2G-student-agreement.html")


@home_blueprint.route("/ferpa", methods=["GET", "POST"])
@cache.cached()
def ferpa():
    return render_template("ferpa.html")


@home_blueprint.route("/i2g-students-preparation", methods=["GET", "POST"])
@cache.cached()
def i2g_students_preparation():
    return render_template("i2g-students-preparation.html")


@home_blueprint.route("/video-preparation", methods=["GET", "POST"])
@cache.cached()
def video_preparation():
    return render_template("video-preparation.html")


@home_blueprint.route("/capstone-purchasing-reimbursement", methods=["GET", "POST"])
@cache.cached()
def capstone_purchasing_reimbursement():
    return render_template("capstone-purchasing-reimbursement.html")


@home_blueprint.route("/contact-us", methods=["GET", "POST"])
@cache.cached()
def contact_us():
    return render_template("contact-us.html")


@home_blueprint.route("/judging", methods=["GET", "POST"])
@cache.cached()
def judging():
    return render_template("judging.html")


@home_blueprint.route("/template", methods=["GET", "POST"])
@cache.cached()
def template():
    return render_template("template.html")


@home_blueprint.route("/template-email-team-students", methods=["GET", "POST"])
@cache.cached()
def template_email_team_students():
    return render_template("template-email-team-students.html")


@home_blueprint.route("/I2G-project-sponsor-acknowledgement", methods=["GET", "POST"])
@cache.cached()
def I2G_project_sponsor_acknowledgement():
    return render_template("I2G-project-sponsor-acknowledgement.html")


@home_blueprint.route("/home-during-event", methods=["GET", "POST"])
@cache.cached()
def home_during_event():
    return render_template("home-during-event.html")


@home_blueprint.route("/home-post-event", methods=["GET", "POST"])
@cache.cached()
def home_post_event():
    return render_template("home-post-event.html")


@home_blueprint.route("/2025-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2025():
    return render_template("2025-fall-event.html")


@home_blueprint.route("/2025-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2025():
    return render_template("2025-spring-event.html")


@home_blueprint.route("/2024-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2024():
    return render_template("2024-fall-event.html")


@home_blueprint.route("/2023-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2023():
    return render_template("2023-fall-event.html")


@home_blueprint.route("/2023-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2023():
    return render_template("2023-spring-event.html")


@home_blueprint.route("/2024-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2024():
    return render_template("2024-spring-event.html")


@home_blueprint.route("/2022-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2022():
    return render_template("2022-fall-event.html")


@home_blueprint.route("/2022-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2022():
    return render_template("2022-spring-event.html")


@home_blueprint.route("/2021-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2021():
    return render_template("2021-spring-event.html")


@home_blueprint.route("/2021-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2021():
    return render_template("2021-fall-event.html")


@home_blueprint.route("/2020-fall-post-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_post_2020():
    return render_template("2020-fall-post-event.html")


@home_blueprint.route("/2014-sponsors", methods=["GET", "POST"])
@cache.cached()
def sponsors_2014():
    return render_template("2014-sponsors.html")


@home_blueprint.route("/2015-sponsors", methods=["GET", "POST"])
@cache.cached()
def sponsors_2015():
    return render_template("2015-sponsors.html")


@home_blueprint.route("/past-projects", methods=["GET", "POST"])
@home_blueprint.route("/past-projects/<uuid_string>", methods=["GET", "POST"])
def past_projects(uuid_string=None):
    wks = gspread.service_account().open("Shareable Merge Tables").worksheet("Sheet1")
    if request.method == "POST":
        data = request.get_json()
        uuid_string = str(uuid.uuid4())

        def update_sheet():
            team_name = ""
            team_number = ""

            for d in data[:-1]:
                team_name += d["Team Name"] + " ; "
                team_number += d["Team#"] + " ; "

            if len(data) > 0:
                team_name += data[-1]["Team Name"]
                team_number += data[-1]["Team#"]

            wks.append_row(values=[uuid_string, team_name, team_number])

        Thread(target=update_sheet).start()

        return jsonify({"uuid_string": uuid_string})

    team_names = []
    team_numbers = []

    if uuid_string is not None:
        cell = wks.find(uuid_string, in_column=1)
        if cell is not None:
            query = wks.row_values(cell.row)
            if len(query) == 3:
                team_names = query[1].split(" ; ")
                team_numbers = query[2].split(" ; ")

    return render_template("past-projects.html", team_names=team_names, team_numbers=team_numbers)
