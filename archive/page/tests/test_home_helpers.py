"""Unit tests for the pure data-transform helpers in project/views/home.py.

These functions contain all the Google-Sheets payload-shaping logic and have
no I/O, so they are tested directly without any mocking.
"""

from types import SimpleNamespace

from project.views import home


# --- small scalar helpers ---------------------------------------------------

def test_normalize_sheet_header_strips_non_alnum_and_lowercases():
    assert home._normalize_sheet_header("Team #") == "team"
    assert home._normalize_sheet_header("Year-Semester") == "yearsemester"
    assert home._normalize_sheet_header("  Zoom live ") == "zoomlive"


def test_coerce_int():
    assert home._coerce_int("12") == 12
    assert home._coerce_int("  7  ") == 7
    assert home._coerce_int("abc") is None
    assert home._coerce_int("") is None
    assert home._coerce_int("-3") is None  # isdigit() is False for negatives


def test_stringify():
    assert home._stringify(None) == ""
    assert home._stringify("  hi  ") == "hi"
    assert home._stringify(5) == "5"


def test_normalize_record_and_get_record_value():
    record = {"Team #": "7", "Project Title": "AI Thing"}
    normalized = home._normalize_record(record)
    assert normalized == {"team": "7", "projecttitle": "AI Thing"}
    assert home._get_record_value(normalized, ["Team#", "Team"]) == "7"
    assert home._get_record_value(normalized, ["Missing"], default="n/a") == "n/a"


# --- current-projects payload ----------------------------------------------

CP_HEADERS = [
    "Track", "Order", "Year-Semester", "Class", "Team#", "TeamName",
    "Project Title", "Organization", "Industry", "Abstract",
    "Student Names", "NameTitle",
]


def test_build_current_projects_payload_maps_aliased_columns():
    rows = [
        CP_HEADERS,
        ["1", "1", "2024-Fall", "CSE", "7", "Rocket", "AI Thing",
         "ACME", "Tech", "Abs", "Alice, Bob", "Dr. X"],
    ]
    payload = home._build_current_projects_payload(rows)
    assert len(payload) == 1
    project = payload[0]
    assert project["Team#"] == "7"
    assert project["TeamName"] == "Rocket"
    assert project["Project Title"] == "AI Thing"
    assert project["Organization"] == "ACME"


def test_build_current_projects_payload_skips_blank_and_empty_rows():
    rows = [
        CP_HEADERS,
        ["", "", "", "", "", "", "", "", "", "", "", ""],     # fully blank -> skipped
        ["9", "1", "2024-Fall", "CSE", "", "", "", "x", "", "", "", ""],  # no team/title -> skipped
        ["1", "1", "2024-Fall", "CSE", "42", "", "Cool", "y", "", "", "", ""],  # kept (team#)
    ]
    payload = home._build_current_projects_payload(rows)
    assert [p["Team#"] for p in payload] == ["42"]


def test_build_current_projects_payload_empty_input():
    assert home._build_current_projects_payload([]) == []


# --- schedule payloads ------------------------------------------------------

def test_build_schedule_tracks_payload_sorts_and_shapes():
    records = [
        {"Track": "2", "Room": "202", "Zoom live": "No", "Class": "ee", "Topic": "Robots"},
        {"Track": "1", "Room": "101", "Zoom live": "Yes", "Class": "cse", "Topic": "AI"},
        {"Track": "x", "Room": "skip"},  # non-int track -> dropped
    ]
    tracks = home._build_schedule_tracks_payload(records)
    assert [t["Track"] for t in tracks] == [1, 2]  # sorted ascending
    assert tracks[0]["Room"] == "101"
    assert tracks[0]["Class"] == "CSE"  # upper-cased
    assert tracks[0]["ZoomLive"] == "Yes"


def test_build_schedule_projects_payload_keeps_breaks_and_sorts():
    records = [
        {"Track": "1", "Order": "2", "Team#": "7", "TeamName": "Rocket",
         "Project Title": "AI", "Organization": "ACME"},
        {"Track": "1", "Order": "1", "Project Title": "break"},  # break row kept
        {"Track": "2", "Order": "1"},  # no identifying fields, not a break -> dropped
    ]
    projects = home._build_schedule_projects_payload(records)
    assert [(p["Track"], p["Order"]) for p in projects] == [(1, 1), (1, 2)]
    assert projects[0]["IsBreak"] is True
    assert projects[1]["IsBreak"] is False
    assert projects[1]["Team#"] == "7"


# --- error-response helper (needs app context for jsonify) ------------------

def test_sheet_api_error_response_403(app):
    exc = SimpleNamespace(response=SimpleNamespace(status_code=403))
    with app.app_context():
        resp, code = home._sheet_api_error_response(exc, "current-projects")
        assert code == 403
        assert "permission denied" in resp.get_json()["error"].lower()


def test_sheet_api_error_response_other_status_is_502(app):
    exc = SimpleNamespace(response=SimpleNamespace(status_code=500))
    with app.app_context():
        resp, code = home._sheet_api_error_response(exc, "schedule")
        assert code == 502
        assert "schedule" in resp.get_json()["error"]
