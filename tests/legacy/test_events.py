import time

from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event
from project import get_wks_columns, wks, get_wks_records, sh
from dataclasses import fields

# def test_no_user_found(client):
#     """
#         Tests if error2.html renders if "membership/event-registration/<event_name>/<token>"
#         API call is sent and there is no matching user with the email in the members sheet
#     """

#     # --- CLEAR MEMBERS SHEET --- #
#     records = get_wks_records(wks)
#     num_records = len(records)
#     if num_records > 1:
#         wks.delete_rows(2, num_records)
#     elif num_records > 0:
#         wks.delete_rows(2)


#     # --- GET EVENT NAME --- #
#     event_name = ""
#     with client.application.app_context():
#         event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
#         event_name = event_obj.name
#         assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"


#     # --- CLEAR EVENT SHEET --- #
#     event_wks = sh.worksheet(event_name)
#     event_records = get_wks_records(event_wks)
#     num_event_records = len(event_records)
#     if num_event_records > 1:
#         event_wks.delete_rows(2, num_event_records)
#     elif num_event_records > 0:
#         event_wks.delete_rows(2)


#     primary_email = "aadhikari4@ucmerced.edu"
#     token = generate_token(primary_email)

#     with client as c:
#         response = c.get(f"/membership/event-registration/{event_name}/{token}")
#         soup = BeautifulSoup(response.data, "html.parser")
#         string = "Your email may have been removed from our database due to not verifying after an extended period of time."
#         find_string = soup.find("p", string=string)
#         assert find_string is not None, "ERROR2 has not been rendered"

def test_happy_path_get(client):
    """
       Testing get requst to "membership/event-registration/<event_name>/<token>"
       Should have the form with prepopulated fields

       Nothing should be in event sheet
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


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]

    primary_email = "test@email.com"
    secondary_email = "test2@email.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email
    assert row["Secondary Email"] == secondary_email
    time.sleep(3)


    token = generate_token(primary_email)
    with client as c:
        response = c.get(f"/membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        print(soup.prettify())
        found_first_name = soup.find("input", {"name": "first_name"})["value"] # type: ignore
        found_last_name = soup.find("input", {"name": "last_name"})["value"] # type: ignore
        found_primary_email = soup.find("input", {"name": "primary_email"})["value"] # type: ignore
        found_secondary_email = soup.find("input", {"name": "secondary_email"})["value"] # type: ignore
        found_register_event = soup.find("input", {"name": "register_event"})["value"] # type: ignore

    assert found_first_name == first_name
    assert found_last_name == last_name
    assert found_primary_email == primary_email, "PRIMARY EMAIL DOES NOT MATCH"
    assert found_secondary_email == secondary_email
    assert found_register_event == 'y'
