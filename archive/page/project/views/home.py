import os
import gspread, uuid
from threading import Thread
from flask import Blueprint, render_template, request, jsonify
from gspread.exceptions import APIError
from project import cache

CURRENT_PROJECTS_SPREADSHEET_ID = "1KRFQ7UX35du1VJCNs4naykynTtLAr0rgtKrNOEWMkgI"
CURRENT_PROJECTS_WORKSHEET_GID = 1913722874
SCHEDULE_TRACKS_WORKSHEET_GID = 1832792385
SERVICE_ACCOUNT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "service_account.json",
)


def _normalize_sheet_header(value):
    return "".join(character.lower() for character in value if character.isalnum())


def _open_spreadsheet(spreadsheet_id):
    return gspread.service_account(filename=SERVICE_ACCOUNT_PATH).open_by_key(
        spreadsheet_id
    )


def _get_worksheet_by_gid(spreadsheet, worksheet_gid):
    return next(
        (worksheet for worksheet in spreadsheet.worksheets() if worksheet.id == worksheet_gid),
        None,
    )


def _coerce_int(value):
    value = str(value).strip()
    return int(value) if value.isdigit() else None


def _normalize_record(record):
    return {_normalize_sheet_header(key): value for key, value in record.items()}


def _get_record_value(normalized_record, aliases, default=""):
    for alias in aliases:
        normalized_alias = _normalize_sheet_header(alias)
        if normalized_alias in normalized_record:
            return normalized_record[normalized_alias]
    return default


def _stringify(value):
    return str(value).strip() if value is not None else ""


def _build_schedule_tracks_payload(records):
    tracks = []

    for record in records:
        normalized_record = _normalize_record(record)
        track_number = _coerce_int(_get_record_value(normalized_record, ["Track"]))
        if track_number is None:
            continue

        tracks.append(
            {
                "Track": track_number,
                "Room": _stringify(_get_record_value(normalized_record, ["Room"])),
                "ZoomLive": _stringify(
                    _get_record_value(normalized_record, ["Zoom live", "Zoom"])
                ),
                "Class": _stringify(_get_record_value(normalized_record, ["Class"])).upper(),
                "Topic": _stringify(_get_record_value(normalized_record, ["Topic"])),
            }
        )

    return sorted(tracks, key=lambda track: track["Track"])


def _build_schedule_projects_payload(records):
    projects = []

    for record in records:
        normalized_record = _normalize_record(record)
        track_number = _coerce_int(_get_record_value(normalized_record, ["Track"]))
        order_number = _coerce_int(_get_record_value(normalized_record, ["Order"]))
        if track_number is None or order_number is None:
            continue

        team_number = _stringify(
            _get_record_value(normalized_record, ["Team#", "Team #", "Team Number", "Team"])
        )
        team_name = _stringify(_get_record_value(normalized_record, ["TeamName", "Team Name"]))
        project_title = _stringify(
            _get_record_value(normalized_record, ["Project Title", "Title"])
        )
        organization = _stringify(
            _get_record_value(normalized_record, ["Organization", "Partner Organization", "Partner"])
        )
        industry = _stringify(_get_record_value(normalized_record, ["Industry"]))
        abstract = _stringify(
            _get_record_value(normalized_record, ["Abstract", "Project Abstract"])
        )
        student_names = _stringify(
            _get_record_value(normalized_record, ["Student Names", "Students"])
        )
        name_title = _stringify(
            _get_record_value(
                normalized_record,
                ["NameTitle", "Name Title", "Name: - Title:", "Contact Name Title"],
            )
        )
        is_break = (
            project_title.lower() == "break"
            or organization.lower() == "break"
            or team_name.lower() == "break"
        )

        if not is_break and not any([team_number, team_name, project_title, organization]):
            continue

        projects.append(
            {
                "Track": track_number,
                "Order": order_number,
                "Year-Semester": _stringify(
                    _get_record_value(normalized_record, ["Year-Semester", "Year Semester", "Semester"])
                ),
                "Class": _stringify(_get_record_value(normalized_record, ["Class"])),
                "Team#": team_number,
                "TeamName": team_name,
                "Project Title": project_title,
                "Organization": organization,
                "Industry": industry,
                "Abstract": abstract,
                "Student Names": student_names,
                "NameTitle": name_title,
                "IsBreak": is_break,
            }
        )

    return sorted(projects, key=lambda project: (project["Track"], project["Order"]))


def _sheet_api_error_response(exc, context_name):
    status_code = exc.response.status_code if exc.response is not None else 502
    if status_code == 403:
        return (
            jsonify(
                {
                    "error": f"Google Sheet permission denied for the {context_name} service account."
                }
            ),
            403,
        )
    return jsonify({"error": f"Unable to load {context_name} data: {exc}"}), 502


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
        spreadsheet = _open_spreadsheet(CURRENT_PROJECTS_SPREADSHEET_ID)
        worksheet = _get_worksheet_by_gid(spreadsheet, CURRENT_PROJECTS_WORKSHEET_GID)

        if worksheet is None:
            return jsonify({"error": "Current projects worksheet not found."}), 404

        rows = worksheet.get("A:Y")
        return jsonify(_build_current_projects_payload(rows))
    except APIError as exc:
        return _sheet_api_error_response(exc, "current-projects")
    except Exception as exc:
        return (
            jsonify({"error": f"Unable to load current projects data: {exc}"}),
            502,
        )


@home_blueprint.route("/api/schedule-data", methods=["GET"])
def schedule_data():
    try:
        spreadsheet = _open_spreadsheet(CURRENT_PROJECTS_SPREADSHEET_ID)
        tracks_worksheet = _get_worksheet_by_gid(spreadsheet, SCHEDULE_TRACKS_WORKSHEET_GID)
        projects_worksheet = _get_worksheet_by_gid(
            spreadsheet, CURRENT_PROJECTS_WORKSHEET_GID
        )

        if tracks_worksheet is None:
            return jsonify({"error": "Schedule tracks worksheet not found."}), 404

        if projects_worksheet is None:
            return jsonify({"error": "Schedule projects worksheet not found."}), 404

        tracks = _build_schedule_tracks_payload(tracks_worksheet.get_all_records())
        projects = _build_schedule_projects_payload(
            projects_worksheet.get_all_records()
        )
        track_class_by_number = {
            track["Track"]: track["Class"] for track in tracks if track.get("Class")
        }
        for project in projects:
            project["Class"] = track_class_by_number.get(
                project["Track"], project["Class"]
            )
        return jsonify({"tracks": tracks, "projects": projects})
    except APIError as exc:
        return _sheet_api_error_response(exc, "schedule")
    except Exception as exc:
        return jsonify({"error": f"Unable to load schedule data: {exc}"}), 502


@home_blueprint.route("/partnership", methods=["GET", "POST"])
@cache.cached()
def partnership():
    return render_template("partnership.html")


@home_blueprint.route("/sponsorship", methods=["GET", "POST"])
@cache.cached()
def sponsorship():
    return render_template("sponsorship.html")


@home_blueprint.route("/i2g-students-preparation", methods=["GET", "POST"])
@cache.cached()
def i2g_students_preparation():
    return render_template("i2g-students-preparation.html")


@home_blueprint.route("/video-preparation", methods=["GET", "POST"])
@cache.cached()
def video_preparation():
    return render_template("video-preparation.html")


@home_blueprint.route("/template", methods=["GET", "POST"])
@cache.cached()
def template():
    return render_template("template.html")


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
