import time

from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event
from project import get_wks_columns, wks, get_wks_records, sh

def test_no_user_fount(client):
    """
        Tests if error2.html renders if "membership/event-registration/<event_name>/<token>"
        API call is sent and there is no matching user with the email in the members sheet
    """

    # --- CLEAR MEMBERS SHEET --- #
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records)
    elif num_records > 0:
        wks.delete_rows(2)


    # --- GET EVENT NAME --- #
    event_name = ""
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"


    # --- CLEAR EVENT SHEET --- #
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    if num_event_records > 1:
        event_wks.delete_rows(2, num_event_records)
    elif num_event_records > 0:
        event_wks.delete_rows(2)


    primary_email = "aadhikari4@ucmerced.edu"
    token = generate_token(primary_email)

    with client as c:
        response = c.get(f"/membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        string = "Your email may have been removed from our database due to not verifying after an extended period of time."
        find_string = soup.find("p", string=string)
        assert find_string is not None, "ERROR2 has not been rendered"
