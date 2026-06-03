"""Tests for the three Google-Sheets-backed routes, with gspread mocked.

These routes reach Sheets lazily (only when hit), so they are tested by
patching ``home._open_spreadsheet`` / ``home.gspread`` — no network or
service-account credentials are required.
"""

from unittest.mock import MagicMock

from project.views import home

CP_HEADERS = [
    "Track", "Order", "Year-Semester", "Class", "Team#", "TeamName",
    "Project Title", "Organization", "Industry", "Abstract",
    "Student Names", "NameTitle",
]


def _fake_worksheet(gid, rows=None, records=None):
    ws = MagicMock()
    ws.id = gid
    if rows is not None:
        ws.get.return_value = rows
    if records is not None:
        ws.get_all_records.return_value = records
    return ws


# --- /api/current-projects --------------------------------------------------

def test_api_current_projects_happy(client, monkeypatch):
    ws = _fake_worksheet(
        home.CURRENT_PROJECTS_WORKSHEET_GID,
        rows=[
            CP_HEADERS,
            ["1", "1", "2024-Fall", "CSE", "7", "Rocket", "AI Thing",
             "ACME", "Tech", "Abs", "Alice, Bob", "Dr. X"],
        ],
    )
    spreadsheet = MagicMock()
    spreadsheet.worksheets.return_value = [ws]
    monkeypatch.setattr(home, "_open_spreadsheet", lambda sid: spreadsheet)

    resp = client.get("/api/current-projects")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert data[0]["Team#"] == "7"
    assert data[0]["Project Title"] == "AI Thing"


def test_api_current_projects_worksheet_missing_404(client, monkeypatch):
    spreadsheet = MagicMock()
    spreadsheet.worksheets.return_value = []  # nothing matches the GID
    monkeypatch.setattr(home, "_open_spreadsheet", lambda sid: spreadsheet)

    resp = client.get("/api/current-projects")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_api_current_projects_unexpected_error_502(client, monkeypatch):
    def boom(_sid):
        raise RuntimeError("network down")

    monkeypatch.setattr(home, "_open_spreadsheet", boom)
    resp = client.get("/api/current-projects")
    assert resp.status_code == 502
    assert "error" in resp.get_json()


# --- /api/schedule-data -----------------------------------------------------

def test_api_schedule_data_happy(client, monkeypatch):
    tracks_ws = _fake_worksheet(
        home.SCHEDULE_TRACKS_WORKSHEET_GID,
        records=[{"Track": "1", "Room": "101", "Zoom live": "Yes",
                  "Class": "cse", "Topic": "AI"}],
    )
    projects_ws = _fake_worksheet(
        home.CURRENT_PROJECTS_WORKSHEET_GID,
        records=[{"Track": "1", "Order": "1", "Team#": "7", "TeamName": "Rocket",
                  "Project Title": "AI", "Organization": "ACME"}],
    )
    spreadsheet = MagicMock()
    spreadsheet.worksheets.return_value = [tracks_ws, projects_ws]
    monkeypatch.setattr(home, "_open_spreadsheet", lambda sid: spreadsheet)

    resp = client.get("/api/schedule-data")
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data) == {"tracks", "projects"}
    assert data["tracks"][0]["Track"] == 1
    assert data["projects"][0]["Team#"] == "7"
    # The track's Class is propagated onto its projects.
    assert data["projects"][0]["Class"] == "CSE"


def test_api_schedule_data_unexpected_error_502(client, monkeypatch):
    def boom(_sid):
        raise RuntimeError("boom")

    monkeypatch.setattr(home, "_open_spreadsheet", boom)
    resp = client.get("/api/schedule-data")
    assert resp.status_code == 502
    assert "error" in resp.get_json()
