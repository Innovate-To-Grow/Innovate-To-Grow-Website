import pytest
from unittest.mock import MagicMock, patch
from project.views.admin import ProspectsView
from gspread.cell import Cell

@pytest.fixture
def mock_admin_deps():
    with patch("project.views.admin.get_wks_records") as mock_get_records, \
         patch("project.views.admin.get_wks_columns") as mock_get_columns, \
         patch("project.views.admin.wks") as mock_wks, \
         patch("project.views.admin.prospects") as mock_prospects_sheet, \
         patch("project.views.admin.flash") as mock_flash, \
         patch("project.views.admin.render_template") as mock_render:
        
        yield {
            "get_records": mock_get_records,
            "get_columns": mock_get_columns,
            "wks": mock_wks,
            "prospects": mock_prospects_sheet,
            "flash": mock_flash,
            "render": mock_render
        }

def test_prospects_no_conflicts(client, mock_admin_deps):
    mock_admin_deps["get_records"].side_effect = [
        [ # Members records
            {"Row": 2, "Primary Email": "member@example.com", "Secondary Email": "", "Phone Number": "1234567890", "When Started": "2023-01-01"}
        ],
        [ # Prospects records
            {"Row": 2, "Email": "new@example.com", "Secondary Email (optional)": "", "Phone Number (optional)": "9876543210", "When signed up as member?": ""}
        ]
    ]
    mock_admin_deps["get_columns"].return_value = {
        "When last checked?": 1,
        "When signed up as member?": 2,
        "Collision?": 3,
        "Secondary Collision": 4,
        "Phone Collision": 5,
        "Notes": 6
    }
    
    with patch("project.views.admin.current_user") as mock_user:
        mock_user.is_authenticated = True
        mock_user.has_role.return_value = True
        
        resp = client.post("/admin/prospects/prospects", data={"check": "Check"})
        
        assert resp.status_code == 200
        mock_admin_deps["prospects"].update_cells.assert_called()
        call_args = mock_admin_deps["prospects"].update_cells.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].col == 1 

def test_prospects_primary_conflict(client, mock_admin_deps):
    mock_admin_deps["get_records"].side_effect = [
        [ # Members
            {"Row": 2, "Primary Email": "conflict@example.com", "Secondary Email": "", "Phone Number": "", "When Started": "2023-01-01"}
        ],
        [ # Prospects
            {"Row": 2, "Email": "conflict@example.com", "Secondary Email (optional)": "", "Phone Number (optional)": "", "When signed up as member?": ""}
        ]
    ]
    mock_admin_deps["get_columns"].return_value = {
        "When last checked?": 1,
        "When signed up as member?": 2,
        "Collision?": 3,
        "Notes": 6
    }
    
    with patch("project.views.admin.current_user") as mock_user:
        mock_user.is_authenticated = True
        client.post("/admin/prospects/prospects", data={"check": "Check"})
        
        call_args = mock_admin_deps["prospects"].update_cells.call_args[0][0]
        collision_cells = [c for c in call_args if c.col == 3 and c.value == "TRUE"]
        assert len(collision_cells) == 1
        
        notes_cells = [c for c in call_args if c.col == 6]
        assert len(notes_cells) == 1
        assert "Primary email found as Primary Email" in notes_cells[0].value

def test_prospects_secondary_conflict(client, mock_admin_deps):
    mock_admin_deps["get_records"].side_effect = [
        [ # Members
            {"Row": 2, "Primary Email": "member@example.com", "Secondary Email": "sec@example.com", "Phone Number": "", "When Started": "2023-01-01"}
        ],
        [ # Prospects
            {"Row": 2, "Email": "other@example.com", "Secondary Email (optional)": "sec@example.com", "Phone Number (optional)": "", "When signed up as member?": ""}
        ]
    ]
    mock_admin_deps["get_columns"].return_value = {
        "When last checked?": 1,
        "Secondary Collision": 4,
        "Notes": 6
    }
    
    with patch("project.views.admin.current_user") as mock_user:
        mock_user.is_authenticated = True
        client.post("/admin/prospects/prospects", data={"check": "Check"})
        
        call_args = mock_admin_deps["prospects"].update_cells.call_args[0][0]
        
        collision_cells = [c for c in call_args if c.col == 4 and c.value == "TRUE"]
        assert len(collision_cells) == 1
        
        notes_cells = [c for c in call_args if c.col == 6]
        assert "Secondary email found as Secondary Email" in notes_cells[0].value

def test_prospects_phone_conflict(client, mock_admin_deps):
    mock_admin_deps["get_records"].side_effect = [
        [ # Members
            {"Row": 2, "Primary Email": "member@example.com", "Secondary Email": "", "Phone Number": "123-456-7890", "When Started": "2023-01-01"}
        ],
        [ # Prospects
            {"Row": 2, "Email": "new@example.com", "Secondary Email (optional)": "", "Phone Number (optional)": "1234567890", "When signed up as member?": ""}
        ]
    ]
    mock_admin_deps["get_columns"].return_value = {
        "When last checked?": 1,
        "Phone Collision": 5,
        "Notes": 6
    }
    
    with patch("project.views.admin.current_user") as mock_user:
        mock_user.is_authenticated = True
        client.post("/admin/prospects/prospects", data={"check": "Check"})
        
        call_args = mock_admin_deps["prospects"].update_cells.call_args[0][0]
        
        collision_cells = [c for c in call_args if c.col == 5 and c.value == "TRUE"]
        assert len(collision_cells) == 1
        
        notes_cells = [c for c in call_args if c.col == 6]
        assert "Phone number found" in notes_cells[0].value

def test_prospects_skip_existing(client, mock_admin_deps):
    mock_admin_deps["get_records"].side_effect = [
        [ # Members
            {"Row": 2, "Primary Email": "member@example.com", "Secondary Email": "", "Phone Number": "", "When Started": ""}
        ],
        [ # Prospects
            {"Row": 2, "Email": "member@example.com", "Secondary Email (optional)": "", "Phone Number (optional)": "", "When signed up as member?": "2023-01-01"}
        ]
    ]
    mock_admin_deps["get_columns"].return_value = {}
    
    with patch("project.views.admin.current_user") as mock_user:
        mock_user.is_authenticated = True
        client.post("/admin/prospects/prospects", data={"check": "Check"})
        
        mock_admin_deps["prospects"].update_cells.assert_not_called()

def test_prospects_mixed_conflict(client, mock_admin_deps):
    mock_admin_deps["get_records"].side_effect = [
        [ # Members
            {"Row": 2, "Primary Email": "primary@example.com", "Secondary Email": "secondary@example.com", "Phone Number": "1234567890", "When Started": "2023-01-01"}
        ],
        [ # Prospects
            {"Row": 2, "Email": "primary@example.com", "Secondary Email (optional)": "secondary@example.com", "Phone Number (optional)": "1234567890", "When signed up as member?": ""}
        ]
    ]
    mock_admin_deps["get_columns"].return_value = {
        "When last checked?": 1,
        "When signed up as member?": 2,
        "Collision?": 3,
        "Secondary Collision": 4,
        "Phone Collision": 5,
        "Notes": 6
    }
    
    with patch("project.views.admin.current_user") as mock_user:
        mock_user.is_authenticated = True
        client.post("/admin/prospects/prospects", data={"check": "Check"})
        
        call_args = mock_admin_deps["prospects"].update_cells.call_args[0][0]
        
        # Expect all collision flags
        primary_coll = [c for c in call_args if c.col == 3 and c.value == "TRUE"]
        assert len(primary_coll) == 1
        
        sec_coll = [c for c in call_args if c.col == 4 and c.value == "TRUE"]
        assert len(sec_coll) == 1
        
        phone_coll = [c for c in call_args if c.col == 5 and c.value == "TRUE"]
        assert len(phone_coll) == 1
        
        notes_cells = [c for c in call_args if c.col == 6]
        assert len(notes_cells) == 1
        note_text = notes_cells[0].value
        assert "Primary email found" in note_text
        assert "Secondary email found" in note_text
        assert "Phone number found" in note_text
