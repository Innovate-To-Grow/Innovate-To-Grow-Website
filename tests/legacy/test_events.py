import time
import re

from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event
from project import get_wks_columns, wks, get_wks_records, sh
from tests.testingHelpers import clear_members_sheet, get_event_info, clear_event_sheet

def test_no_user_found(client):
    """
        Tests if error2.html renders if "membership/event-registration/<event_name>/<token>"
        API call is sent and there is no matching user with the email in the members sheet
    """


    # --- CLEAR MEMBERS SHEET --- #
    records = get_wks_records(wks)
    # print("records:")
    # print(records)
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


def test_happy_path_get(client):
    """
       Testing get requst to "membership/event-registration/<event_name>/<token>"
       Should have the form with prepopulated fields without event stuff

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
    time.sleep(3)

    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email
    assert row["Secondary Email"] == secondary_email

    token = generate_token(primary_email)
    with client as c:
        response = c.get(f"/membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)
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

    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    assert num_event_records == 0


def test_happy_path_get_already_registered(client):
    """
        Tests for happy path of get reqeust when the user has already been signed up
        should have prepopulated fields for everything
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
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"


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
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email
    assert row["Secondary Email"] == secondary_email

    # --- ADD ROW OF DATA TO EVENT SHEET --- #
    event_wks_columns = get_wks_columns(event_wks)
    event_user = ["" for i in range(len(event_wks_columns))]
    event_user[event_wks_columns["Order"] - 1] = "1"
    event_user[event_wks_columns["First Name"] - 1] = first_name
    event_user[event_wks_columns["Last Name"] - 1] = last_name
    event_user[event_wks_columns["When Started"] - 1 ] = start
    event_user[event_wks_columns["Last Updated"] - 1] = update
    event_user[event_wks_columns["Membership Primary"] - 1] = primary_email
    event_user[event_wks_columns["Membership Secondary"] - 1] = secondary_email
    event_user[event_wks_columns["Ticket Type"] - 1] = ticket

    for question in questions:
        event_user[event_wks_columns[question] - 1] = questions[question]

    event_wks.append_row(event_user)

    # --- MAKE SURE WE ADDED ROW PROPERLY --- #
    event_records = get_wks_records(event_wks)
    event_row = event_records[0]
    assert event_row["Membership Primary"] == primary_email, "PRIMARY EMAIL NOT UPDATED IN SET UP IN EVENT SHEET"
    assert event_row["Membership Secondary"] == secondary_email, "SECONDARY EMAIL NOT UPDATED IN SET UP IN EVENT SHEET"
    assert event_row["First Name"] == first_name, "FIRST NAME NOT UPDATED IN SET UP IN EVENT SHEET"
    assert event_row["Last Name"] == last_name, "LAST NAME NOT UPDATED IN SET UP IN EVENT SHEET"
    assert event_row["When Started"] == start, "WHEN STARTED NOT UPDATED IN SET UP IN EVENT SHEET"
    assert event_row["Last Updated"] == update, "WHEN UPDATED NOT UPDATED IN SET UP IN EVENT SHEET"
    assert event_row["Ticket Type"] == ticket, "TICKET NOT UPDATED IN SET UP IN EVENT SHEET"

    counter = 1
    for question in questions:
        assert event_row[question] == base_answer + str(counter), f"QUESTION {counter} NOT UPDATED IN SET UP"
        counter += 1


    token = generate_token(primary_email)
    found_questions = []

    with client as c:
        response = c.get(f"/membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        found_first_name = soup.find("input", {"name": "first_name"})["value"] # type: ignore
        found_last_name = soup.find("input", {"name": "last_name"})["value"] # type: ignore
        found_primary_email = soup.find("input", {"name": "primary_email"})["value"] # type: ignore
        found_secondary_email = soup.find("input", {"name": "secondary_email"})["value"] # type: ignore
        found_register_event = soup.find("input", {"name": "register_event"})["value"] # type: ignore
        found_checked_ticket = soup.find("input", {"name": "event_tickets", "checked": ""})["value"] # type: ignore
        found_questions = soup.find_all("input", attrs={"name": re.compile(r"^event_Test")})

    assert found_first_name == first_name
    assert found_last_name == last_name
    assert found_primary_email == primary_email, "PRIMARY EMAIL DOES NOT MATCH"
    assert found_secondary_email == secondary_email, "SECONDARY EMAIL DOES NOT MATCH"
    assert found_register_event == 'y', "EVENT IS NOT AUTOSELECTED TO BE REGISTERED"
    assert found_checked_ticket == ticket, "TICKET DOES NOT MATCH"

    counter = 1
    for question in found_questions:
        assert question["value"] == base_answer + str(counter), f"QUESTION {counter} does not match" # type: ignore
        counter += 1

def test_event_post_happy(client):
    """
        This tests for when an event registration happens. This should redirect to the
        receipt page and have the correct info in the members and event sheets
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
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"


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
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email
    assert row["Secondary Email"] == secondary_email

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        assert num_event_records == 1
        row = event_records[0]
        assert row["Membership Primary"] == primary_email
        assert row["Membership Secondary"] == secondary_email
        assert row["Ticket Type"] == ticket

def test_swap_info(client):
    """
        This tests for when we swap primary and secondary emails on an event registration.
    """

    # --- CLEAR MEMBERS SHEET --- #
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # --- GET EVENT NAME --- #
    event_name = ""
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1

    # --- CLEAR EVENT SHEET --- #
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    if num_event_records > 1:
        event_wks.delete_rows(2, num_event_records + 1)
    elif num_event_records > 0:
        event_wks.delete_rows(2)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]

    primary_email = "test@email.com"
    secondary_email = "test2@email.com"
    secondary_email2 = "test3@email.com"
    first_name = "TEST FIRST NAME"
    first_name2 = "TEST2 FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email
    assert row["Secondary Email"] == secondary_email

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name2,
        "last_name": last_name,
        "primary_email": secondary_email,
        "confirm_primary": secondary_email,
        "secondary_email": primary_email,
        "confirm_secondary": primary_email,
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1

    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == secondary_email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == primary_email, "sec email wrong in members sheet"
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == secondary_email, "Primary email wrong in event sheet"
        assert row["Membership Secondary"] == primary_email, "Secondary email wrong in event sheet"


def test_new_prim_same_sec(client):
    """
        This tests for when an event registration has a new primary email and the same secondary email. This
        should work as there are no conflicts.
    """

    # --- CLEAR MEMBERS SHEET --- #
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # --- GET EVENT NAME --- #
    event_name = ""
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1

    # --- CLEAR EVENT SHEET --- #
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    if num_event_records > 1:
        event_wks.delete_rows(2, num_event_records + 1)
    elif num_event_records > 0:
        event_wks.delete_rows(2)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]

    primary_email = "test@email.com"
    secondary_email = "test2@email.com"
    primary_email2 = "test3@email.com"
    first_name = "TEST FIRST NAME"
    first_name2 = "TEST2 FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email
    assert row["Secondary Email"] == secondary_email

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name2,
        "last_name": last_name,
        "primary_email": primary_email2,
        "confirm_primary": primary_email2,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1

    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email2, "prim email wrong in members sheet"
        assert row["Secondary Email"] == secondary_email, "sec email wrong in members sheet"
        event_records = get_wks_records(event_wks)
        event_row = event_records[0]
        assert event_row["Membership Primary"] == primary_email2, "Primary email wrong in event sheet"
        assert event_row["Membership Secondary"] == secondary_email, "Secondary email wrong in event sheet"


def test_new_sec_same_prim(client):
    """
        This tests for when an event registration has a new secondary email and the same primary email. This
        should work as there are no conflicts.
    """

    # --- CLEAR MEMBERS SHEET --- #
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # --- GET EVENT NAME --- #
    event_name = ""
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1

    # --- CLEAR EVENT SHEET --- #
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    if num_event_records > 1:
        event_wks.delete_rows(2, num_event_records + 1)
    elif num_event_records > 0:
        event_wks.delete_rows(2)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]

    primary_email = "test@email.com"
    secondary_email = "test2@email.com"
    secondary_email2 = "test3@email.com"
    first_name = "TEST FIRST NAME"
    first_name2 = "TEST2 FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email
    assert row["Secondary Email"] == secondary_email

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name2,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email2,
        "confirm_secondary": secondary_email2,
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1

    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == secondary_email2, "sec email wrong in members sheet"
        event_records = get_wks_records(event_wks)
        event_row = event_records[0]
        assert event_row["Membership Primary"] == primary_email, "Primary email wrong in event sheet"
        assert event_row["Membership Secondary"] == secondary_email2, "Secondary email wrong in event sheet"


def test_bad_token(client):
    """
        This tests for a bad input token. This should render to the email form.
    """

    # --- CLEAR MEMBERS SHEET --- #
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # --- GET EVENT NAME --- #
    event_name = ""
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1

    # --- CLEAR EVENT SHEET --- #
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    if num_event_records > 1:
        event_wks.delete_rows(2, num_event_records + 1)
    elif num_event_records > 0:
        event_wks.delete_rows(2)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]

    primary_email = "test@email.com"
    secondary_email = "test2@email.com"
    secondary_email2 = "test3@email.com"
    first_name = "TEST FIRST NAME"
    first_name2 = "TEST2 FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email
    assert row["Secondary Email"] == secondary_email

    token = "1111"

    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}", follow_redirects=True)
        soup = BeautifulSoup(response.data, "html.parser")
        found_email_form = soup.find("input", {"name": "email"})
        assert found_email_form is not None, "DID NOT REDIRECT TO THE EMAIL FORM"


def test_1_email_1_phone_number_happy_post(client):
    """
        This tests for an event registration with one email and one phone number.
        It should redirect to the receipt page and the fields in the event and members
        sheet should be appropriately filled.
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
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1


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
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        assert num_event_records == 1
        row = event_records[0]
        assert row["Membership Primary"] == primary_email
        assert row["Phone Number"] == int(phone_number[1:])
        assert row["Ticket Type"] == ticket


def test_2_email_1_phone_happy_post(client):
    """
        This tests for an event registration with two email and one phone number.
        It should redirect to the receipt page and the fields in the event and members
        sheet should be appropriately filled.
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
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1


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
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        # print(soup)
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        assert num_event_records == 1
        row = event_records[0]
        assert row["Membership Primary"] == primary_email
        assert row["Phone Number"] == int(phone_number[1:])
        assert row["Ticket Type"] == ticket
        assert row["Membership Secondary"] == secondary_email



def test_swap_2_emails_to_2_emails_with_phone(client):
    """
        This tests for when the user originally registers with just 2 emails and they do
        event-registration to use 2 emails and 1 phone.
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
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1


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
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h4", string=f"Verify Your Phone Number")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        assert num_event_records == 1
        event_row = event_records[0]
        assert event_row["Membership Primary"] == primary_email
        assert event_row["Phone Number"] == int(phone_number[1:])
        assert event_row["Ticket Type"] == ticket
        assert event_row["Membership Secondary"] == secondary_email

        wks_records = get_wks_records(wks)
        num_wks_records = len(wks_records)
        assert num_wks_records == 1
        row = wks_records[0]
        assert row["Primary Email"] == primary_email
        assert row["Phone Number"] == int(phone_number[1:])
        assert row["Secondary Email"] == secondary_email


def test_swap_2_emails_to_2_emails_with_phone_used(client):
    """
        This tests for when the user originally registers with just 2 emails and they do
        event-registration to use 2 emails and 1 phone.
    """

    # --- CLEAR MEMBERS SHEET --- #
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # --- GET EVENT NAME --- #
    event_name = ""
    ticket = ""
    questions = {}
    counter = 1
    base_answer = "test answer from test_registration_happy: "
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        ticket = ticket_types[0]
        for question in event_obj.questions.split("\n"):
            questions[question] = base_answer + str(counter)
            counter += 1


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
    secondary_email = "test2@email2.com"
    primary_email2 = "wrong@email.com"
    secondary_email2 = "wrong2@email.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email2
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = secondary_email2
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    wks.append_row(user)
    time.sleep(3)


    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)
        heading = soup.find("h1", string=f"ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."


def test_swap_2_email_to_1_email_1_phone_happy(client):
    """
        This tests for when a user originally registered with 2 emails. The user then decides to change
        their information to 1 email and 1 phone number. We expect the otp form to render because the user
        should have to verify their phone number. We also expect in the member and event sheet that they
        have their information changed from the two emails to 1 email 1 phone.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]

    primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1

    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h4", string=f"Verify Your Phone Number")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        assert num_event_records == 1
        event_row = event_records[0]
        assert event_row["Membership Primary"] == primary_email
        assert event_row["Phone Number"] == int(phone_number[1:])
        assert event_row["Ticket Type"] == ticket
        assert event_row["Membership Secondary"] == ""

        wks_records = get_wks_records(wks)
        num_wks_records = len(wks_records)
        assert num_wks_records == 1
        row = wks_records[0]
        assert row["Primary Email"] == primary_email
        assert row["Phone Number"] == int(phone_number[1:])
        assert row["Secondary Email"] == ""
        assert row["Secondary Verified"] == ""
        assert row["Secondary Subscribed"] == ""
        assert row["Secondary Expired"] == ""


def test_swap_2_email_to_1_email_1_phone_with_num_in_use(client):
    """
        This tests for when a user has been registered with 2 emails. They decide to switch to
        one phone number and one email, but the phone number they choose is already in use by another user.
        The error3 template should render and nothing should be added to the event sheet
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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
    time.sleep(3)

    primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    primary_email2 = "wrong@email.com"
    secondary_email2 = "wrong2@email.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == primary_email

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email2
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = secondary_email2
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    wks.append_row(user)
    time.sleep(3)


    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f"ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        assert num_event_records == 0


def test_swap_1_email_1_phone_to_2_email(client):
    """
    This tests for when a user originially registered with 1 email 1 phone number
    but later switches to 2 emails instead.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"
    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == secondary_email, "sec email wrong in members sheet"
        assert row["Phone Number"] == "", "phone number not deleted in members sheet"
        assert row["Phone number subscribed"] == "", "Phone number subscribe field not deleted in members sheet"
        assert row["Phone number verified"] == "", "Phone number verified field not deleted in members sheet"
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email wrong in event sheet"
        assert row["Membership Secondary"] == secondary_email, "Secondary email wrong in event sheet"
        assert row["Phone Number"] == "", "phone number not deleted in events sheet"


def test_swap_1_email_1_phone_to_2_email_1_phone(client):
    """
    This tests for when a user originally registered with 1 email 1 phone number
    but later switches to 2 emails and keeps the phone number.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"
    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == secondary_email, "sec email wrong in members sheet"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number deleted in members sheet when it should be kept"
        assert row["Phone number subscribed"] == "TRUE", "Phone number subscribe field deleted in members sheet when it should be kept"
        assert row["Phone number verified"] == "TRUE", "Phone number verified field deleted in members sheet when it should be kept"
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email wrong in event sheet"
        assert row["Membership Secondary"] == secondary_email, "Secondary email wrong in event sheet"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number deleted in events sheet when it should be kept"


def test_swap_1_email_1_phone_to_1_email_new_phone(client):
    """
    This tests for when a user originally registered with 1 email 1 phone number
    but later changes to the same email with a different phone number.
    Should show OTP verification form since it's a new phone number.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    old_phone_number = "+18057105809"
    new_phone_number = "+12092591247"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"
    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "2092591247",  # New phone number without country code
        "confirm_phone_number": "2092591247",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h4", string=f"Verify Your Phone Number")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The OTP verification page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email wrong in members sheet"
        assert row["Secondary Email"] == "", "secondary email should be empty in members sheet"
        assert row["Phone Number"] == int(new_phone_number[1:]), "new phone number not updated in members sheet"
        assert row["Phone number subscribed"] == "TRUE", "Phone number subscribe field should be TRUE in members sheet"
        assert row["Phone number verified"] == "FALSE", "Phone number verified field should be FALSE since it's a new number"

        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email wrong in event sheet"
        assert row["Membership Secondary"] == "", "Secondary email should be empty in event sheet"
        assert row["Phone Number"] == int(new_phone_number[1:]), "new phone number not updated in events sheet"


def test_swap_2_email_1_phone_to_2_email(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    but later switches to just 2 emails (removes the phone number).
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"
    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email wrong in members sheet"
        assert row["Secondary Email"] == secondary_email, "secondary email wrong in members sheet"
        assert row["Phone Number"] == "", "phone number not cleared in members sheet"
        assert row["Phone number subscribed"] == "", "Phone number subscribe field not cleared in members sheet"
        assert row["Phone number verified"] == "", "Phone number verified field not cleared in members sheet"
        
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email wrong in event sheet"
        assert row["Membership Secondary"] == secondary_email, "Secondary email wrong in event sheet"
        assert row["Phone Number"] == "", "phone number not cleared in events sheet"


def test_swap_2_email_1_phone_to_1_email_1_phone(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    but later switches to just 1 email and 1 phone number (removes secondary email).
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"
    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User keeps same primary email and phone number, but removes secondary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "8057105809",  # Same phone number without country code
        "confirm_phone_number": "8057105809",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
        # Note: No secondary_email fields - this indicates removal
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email wrong in members sheet"
        assert row["Secondary Email"] == "", "secondary email not deleted in members sheet"
        assert row["Secondary Verified"] == "", "Secondary verified field not cleared in members sheet"
        assert row["Secondary Subscribed"] == "", "Secondary subscribed field not cleared in members sheet"
        assert row["Secondary Expired"] == "", "Secondary expired field not cleared in members sheet"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in members sheet when it should stay the same"
        assert row["Phone number subscribed"] == "TRUE", "Phone number subscribe field changed in members sheet"
        assert row["Phone number verified"] == "TRUE", "Phone number verified field changed in members sheet"
        
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email wrong in event sheet"
        assert row["Membership Secondary"] == "", "Secondary email not deleted in event sheet"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in events sheet when it should stay the same"


def test_swap_2_email_1_phone_to_1_email_1_phone_with_phone_in_use(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    but wants to switch to 1 email and 1 phone number. However, the phone number
    they want to use is already taken by another user. Should render ERROR 03.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    original_phone_number = "+18057105809"  # User's current phone number
    desired_phone_number = "+15551234567"  # This will be taken by another user

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
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
    user[wks_columns["Phone Number"] - 1] = original_phone_number  # User starts with a phone number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"
    wks.append_row(user)
    time.sleep(3)

    # --- ADD SECOND USER TO MEMBERS SHEET (who already has the desired phone number) --- #
    user2 = ["" for i in range(len(wks_columns))]
    primary_email2 = "other@email.com"
    secondary_email2 = "other2@email.com"
    first_name2 = "OTHER FIRST NAME"
    last_name2 = "OTHER LAST NAME"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start
    user2[wks_columns["Last Updated"] - 1] = update
    user2[wks_columns["Primary Email"] - 1] = primary_email2
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = secondary_email2
    user2[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = desired_phone_number  # This phone is already taken
    user2[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user2[wks_columns["Phone number verified"] - 1] = "TRUE"
    wks.append_row(user2)
    time.sleep(3)

    # Verify we have two users in the sheet
    records = get_wks_records(wks)
    assert len(records) == 2
    assert records[0]["Primary Email"] == primary_email
    assert records[0]["Secondary Email"] == secondary_email
    assert records[0]["Phone Number"] == int(original_phone_number[1:])
    assert records[1]["Primary Email"] == primary_email2
    assert records[1]["Phone Number"] == int(desired_phone_number[1:])

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # First user tries to switch from 2 emails to 1 email + phone number that's already taken
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "5551234567",  # Phone number already in use by user2
        "confirm_phone_number": "5551234567",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
        # Note: No secondary_email fields - user is removing secondary email
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1

    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f"ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        # Verify no event record was created due to the conflict
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        assert num_event_records == 0, "Event record was created despite phone number conflict"

        # Verify original user data is unchanged
        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        original_user = records[0]
        assert original_user["Primary Email"] == primary_email, "Original user primary email changed"
        assert original_user["Secondary Email"] == secondary_email, "Original user secondary email changed"
        assert original_user["Phone Number"] == int(original_phone_number[1:]), "Original user phone number changed when it should remain the same"


def test_swap_2_email_1_phone_change_primary_email(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    but later changes their primary email while keeping secondary email and phone number.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    new_primary_email = "newemail@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = original_primary_email
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
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"
    wks.append_row(user)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User changes primary email but keeps secondary email and phone number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": new_primary_email,  # Changed primary email
        "confirm_primary": new_primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",  # Same phone number without country code
        "confirm_phone_number": "8057105809",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == new_primary_email, "primary email not updated in members sheet"
        assert row["Secondary Email"] == secondary_email, "secondary email changed in members sheet when it should stay the same"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in members sheet when it should stay the same"
        assert row["Phone number subscribed"] == "TRUE", "Phone number subscribe field changed in members sheet"
        assert row["Phone number verified"] == "TRUE", "Phone number verified field changed in members sheet"
        
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == new_primary_email, "Primary email not updated in event sheet"
        assert row["Membership Secondary"] == secondary_email, "Secondary email changed in event sheet when it should stay the same"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in events sheet when it should stay the same"


def test_swap_2_email_1_phone_change_primary_email_to_existing(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    but tries to change their primary email to one that's already in use by another user.
    Should render error4.html.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = original_primary_email
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
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"


    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    taken_primary_email = "taken@email.com"  # This is the email first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = taken_primary_email
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = ""
    user2[wks_columns["Secondary Verified"] - 1] = ""
    user2[wks_columns["Secondary Subscribed"] - 1] = ""
    user2[wks_columns["Secondary Expired"] - 1] = ""
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change primary email to one already in use
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": taken_primary_email,  # Trying to use email that belongs to second user
        "confirm_primary": taken_primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "n",
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == original_primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == taken_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == "", "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_swap_2_email_1_phone_change_primary_email_to_existing_secondary(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    but tries to change their primary email to one that's already in use as another user's secondary email.
    Should render error4.html.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = original_primary_email
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
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the secondary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    other_primary_email = "otherprimary@email.com"
    taken_secondary_email = "takensecondary@email.com"  # This is the email first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = other_primary_email
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = taken_secondary_email  # This is what user 1 wants
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change primary email to one already in use as another user's secondary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": taken_secondary_email,  # Trying to use email that belongs to second user as secondary
        "confirm_primary": taken_secondary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "n",
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == original_primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == other_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == taken_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_swap_2_email_1_phone_change_secondary_email_success(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    and changes their secondary email to a new email that's not in use. Should succeed.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_secondary_email = "test2@email2.com"
    new_secondary_email = "newsecondary@email.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = old_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User changes secondary email to a new email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": new_secondary_email,  # Change to new secondary email
        "confirm_secondary": new_secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == new_secondary_email, "secondary email not updated in members sheet"
        assert row["Phone number subscribed"] == "TRUE", "Phone number subscribe field changed in members sheet"
        assert row["Phone number verified"] == "TRUE", "Phone number verified field changed in members sheet"
        
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email changed in event sheet when it should stay the same"
        assert row["Membership Secondary"] == new_secondary_email, "Secondary email not updated in event sheet"


def test_swap_2_email_1_phone_change_secondary_email_to_existing_secondary(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    but tries to change their secondary email to one that's already in use as another user's secondary email.
    Should render error4.html.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = old_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the secondary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    other_primary_email = "otherprimary@email.com"
    taken_secondary_email = "takensecondary@email.com"  # This is the email first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = other_primary_email
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = taken_secondary_email  # This is what user 1 wants
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change secondary email to one already in use as another user's secondary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": taken_secondary_email,  # Trying to use email that belongs to second user as secondary
        "confirm_secondary": taken_secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == old_secondary_email, "First user secondary email changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == other_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == taken_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_swap_2_email_1_phone_change_secondary_email_to_existing_primary(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone number
    but tries to change their secondary email to one that's already in use as another user's primary email.
    Should render error4.html.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"
    phone_number = "+18057105809"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = old_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the primary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    taken_primary_email = "takenprimary@email.com"  # This is the email first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = taken_primary_email  # This is what user 1 wants
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = ""
    user2[wks_columns["Secondary Verified"] - 1] = ""
    user2[wks_columns["Secondary Subscribed"] - 1] = ""
    user2[wks_columns["Secondary Expired"] - 1] = ""
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change secondary email to one already in use as another user's primary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": taken_primary_email,  # Trying to use email that belongs to second user as primary
        "confirm_secondary": taken_primary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "phone_number": "8057105809",
        "confirm_phone_number": "8057105809",
        "phone_subscribe": "y",
        "country_code": "+1",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == old_secondary_email, "First user secondary email changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == taken_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == "", "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_swap_2_email_change_primary_email_success(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and changes their primary email to a new email that's not in use. Should succeed.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    old_primary_email = "test@email.com"
    new_primary_email = "newprimary@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = old_primary_email
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
    user[wks_columns["Phone Number"] - 1] = ""
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(old_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User changes primary email to a new email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": new_primary_email,  # Change to new primary email
        "confirm_primary": new_primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "n",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == new_primary_email, "primary email not updated in members sheet"
        assert row["Secondary Email"] == secondary_email, "secondary email changed in members sheet when it should stay the same"
        assert row["Phone Number"] == "", "phone number field changed in members sheet when it should stay empty"
        
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == new_primary_email, "Primary email not updated in event sheet"
        assert row["Membership Secondary"] == secondary_email, "Secondary email changed in event sheet when it should stay the same"
        assert row["Phone Number"] == "", "phone number field changed in events sheet when it should stay empty"


def test_swap_2_email_change_primary_email_to_existing_primary(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    but tries to change their primary email to one that's already in use as another user's primary email.
    Should render error4.html.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = original_primary_email
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
    user[wks_columns["Phone Number"] - 1] = ""
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the primary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    taken_primary_email = "takenprimary@email.com"  # This is the email first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = taken_primary_email  # This is what user 1 wants
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = ""
    user2[wks_columns["Secondary Verified"] - 1] = ""
    user2[wks_columns["Secondary Subscribed"] - 1] = ""
    user2[wks_columns["Secondary Expired"] - 1] = ""
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change primary email to one already in use as another user's primary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": taken_primary_email,  # Trying to use email that belongs to second user as primary
        "confirm_primary": taken_primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "n",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == original_primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == taken_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == "", "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_swap_2_email_change_primary_email_to_existing_secondary(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    but tries to change their primary email to one that's already in use as another user's secondary email.
    Should render error4.html.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = original_primary_email
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
    user[wks_columns["Phone Number"] - 1] = ""
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the secondary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    other_primary_email = "otherprimary@email.com"
    taken_secondary_email = "takensecondary@email.com"  # This is the email first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = other_primary_email
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = taken_secondary_email  # This is what user 1 wants
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change primary email to one already in use as another user's secondary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": taken_secondary_email,  # Trying to use email that belongs to second user as secondary
        "confirm_primary": taken_secondary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "n",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == original_primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == other_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == taken_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_swap_2_email_change_secondary_email_success(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and changes their secondary email to a new email that's not in use. Should succeed.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_secondary_email = "test2@email2.com"
    new_secondary_email = "newsecondary@email.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = old_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User changes secondary email to a new email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": new_secondary_email,  # Change to new secondary email
        "confirm_secondary": new_secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string=f" {event_name} Registration Completed ")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == new_secondary_email, "secondary email not updated in members sheet"
        assert row["Phone Number"] == "", "phone number field changed in members sheet when it should stay empty"
        
        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email changed in event sheet when it should stay the same"
        assert row["Membership Secondary"] == new_secondary_email, "Secondary email not updated in event sheet"
        assert row["Phone Number"] == "", "phone number field changed in events sheet when it should stay empty"


def test_swap_2_email_change_secondary_email_to_existing_primary(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    but tries to change their secondary email to one that's already in use as another user's primary email.
    Should render error4.html.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = old_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the primary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    taken_primary_email = "takenprimary@email.com"  # This is the email first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = taken_primary_email  # This is what user 1 wants
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = ""
    user2[wks_columns["Secondary Verified"] - 1] = ""
    user2[wks_columns["Secondary Subscribed"] - 1] = ""
    user2[wks_columns["Secondary Expired"] - 1] = ""
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change secondary email to one already in use as another user's primary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": taken_primary_email,  # Trying to use email that belongs to second user as primary
        "confirm_secondary": taken_primary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == old_secondary_email, "First user secondary email changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == taken_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == "", "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_swap_2_email_change_secondary_email_to_existing_secondary(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    but tries to change their secondary email to one that's already in use as another user's secondary email.
    Should render error4.html.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_secondary_email = "test2@email2.com"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = old_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the secondary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    other_primary_email = "otherprimary@email.com"
    taken_secondary_email = "takensecondary@email.com"  # This is the email first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = other_primary_email
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = taken_secondary_email  # This is what user 1 wants
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change secondary email to one already in use as another user's secondary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": taken_secondary_email,  # Trying to use email that belongs to second user as secondary
        "confirm_secondary": taken_secondary_email,
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == old_secondary_email, "First user secondary email changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == other_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == taken_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_swap_1_email_1_phone_change_phone_number_otp(client):
    """
    This tests for when a user originally registered with 1 email and 1 phone
    and changes their phone number to a new number. Should render OTP verification form.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_phone_number = "+12345678901"
    new_phone_number = "+18057105809"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = ""
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User changes phone number to a new number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "phone_number": "8057105809",  # Change to new phone number
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Important: include phone_subscribe
        "primary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)
        heading = soup.find("h4", string="Verify Your Phone Number")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The OTP verification page was not rendered. The phone verification may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == "", "secondary email field changed in members sheet when it should stay empty"
        assert row["Phone Number"] == int(new_phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number verified"] == "FALSE", "phone number verification should be FALSE for new number"


def test_swap_1_email_1_phone_change_phone_number_in_use(client):
    """
    This tests for when a user originally registered with 1 email and 1 phone
    and tries to change their phone number to one that's already in use by another user.
    Should render ERROR 03.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    original_phone_number = "+12345678901"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = ""
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = original_phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the phone number the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    primary_email2 = "other@email.com"
    taken_phone_number = "+18057105809"  # This is the phone number first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = primary_email2
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = ""
    user2[wks_columns["Secondary Verified"] - 1] = ""
    user2[wks_columns["Secondary Subscribed"] - 1] = ""
    user2[wks_columns["Secondary Expired"] - 1] = ""
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = taken_phone_number  # This is what user 1 wants
    user2[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user2[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change phone number to one already in use by another user
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "phone_number": "8057105809",  # Trying to use phone number that belongs to second user
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Important: include phone_subscribe
        "primary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == "", "First user secondary email changed"
        assert first_user["Phone Number"] == int(original_phone_number[1:]), "First user phone number changed when it should remain the same"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == primary_email2, "Second user primary email changed"
        assert second_user["Secondary Email"] == "", "Second user secondary email changed"
        assert second_user["Phone Number"] == int(taken_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to phone number conflict"


def test_swap_2_email_1_phone_change_phone_number_otp(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and changes their phone number to a new number. Should render OTP verification form.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)


    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
    old_phone_number = "+12345678901"
    new_phone_number = "+18057105809"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User changes phone number to a new number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",  # Change to new phone number
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Important: include phone_subscribe
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h4", string="Verify Your Phone Number")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The OTP verification page was not rendered. The phone verification may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == secondary_email, "secondary email changed in members sheet when it should stay the same"
        assert row["Phone Number"] == int(new_phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number verified"] == "FALSE", "phone number verification should be FALSE for new number"


def test_swap_2_email_1_phone_change_phone_number_in_use(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and tries to change their phone number to one that's already in use by another user.
    Should render ERROR 03.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
    original_phone_number = "+12345678901"
    first_name = "TEST FIRST NAME"
    last_name = "TEST LAST NAME"
    start = "TEST START"
    update = "TEST UPDATE"

    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = first_name
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = original_phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the phone number the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    primary_email2 = "other@email.com"
    secondary_email2 = "othersecondary@email.com"
    taken_phone_number = "+18057105809"  # This is the phone number first user will try to use
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = primary_email2
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = secondary_email2
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = taken_phone_number  # This is what user 1 wants
    user2[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user2[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore


    # --- BUILD FORM DATA --- #
    # User tries to change phone number to one already in use by another user
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",  # Trying to use phone number that belongs to second user
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Important: include phone_subscribe
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }

    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"

    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1


    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == int(original_phone_number[1:]), "First user phone number changed when it should remain the same"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == primary_email2, "Second user primary email changed"
        assert second_user["Secondary Email"] == secondary_email2, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(taken_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to phone number conflict"


def test_otp_form_renders_for_unverified_phone(client):
    """
    Tests that the OTP form renders when a user has a phone number that is not verified.
    User should have phone number "+18057105809" with "FALSE" for phone number verified.
    """
    
    # --- CLEAR MEMBERS SHEET --- #
    clear_members_sheet(wks)
    
    # --- GET EVENT NAME --- #
    event_name, ticket, questions, base_answer = get_event_info(client)
    
    # --- CLEAR EVENT SHEET --- #
    event_wks = clear_event_sheet(sh, event_name)
    
    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    phone_number = "+18057105809"
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
    user[wks_columns["Secondary Email"] - 1] = ""
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "FALSE"  # Phone not verified
    
    wks.append_row(user)
    time.sleep(3)
    
    token = generate_token(primary_email)
    
    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore
    
    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "8057105809",  # Same phone number as in database
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",
        "primary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }
    
    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"
    
    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1
    
    # --- SUBMIT FORM AND CHECK FOR OTP PAGE --- #
    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)
        
        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)
        heading = soup.find("h4", string="Verify Your Phone Number")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The OTP verification page was not rendered. The phone verification may have failed."
        
        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number verified"] == "FALSE", "phone number verification should remain FALSE"


def test_verified_phone_no_otp_required(client):
    """
    Tests that users with already verified phone numbers do NOT get redirected to OTP verification.
    User should have phone number "+18057105809" with "TRUE" for phone number verified.
    """
    
    # --- CLEAR MEMBERS SHEET --- #
    clear_members_sheet(wks)
    
    # --- GET EVENT NAME --- #
    event_name, ticket, questions, base_answer = get_event_info(client)
    
    # --- CLEAR EVENT SHEET --- #
    event_wks = clear_event_sheet(sh, event_name)
    
    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    phone_number = "+18057105809"
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
    user[wks_columns["Secondary Email"] - 1] = ""
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"  # Phone already verified
    
    wks.append_row(user)
    time.sleep(3)
    
    token = generate_token(primary_email)
    
    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore
    
    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "8057105809",  # Same phone number as in database
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",
        "primary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }
    
    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"
    
    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1
    
    # --- SUBMIT FORM AND CHECK FOR SUCCESS PAGE (NOT OTP) --- #
    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)
        
        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)
        
        # Should show success page, NOT OTP page
        success_heading = soup.find("p", string=f"You have successfully registered for {event_name} ")
        print(event_name)
        print(success_heading)
        otp_heading = soup.find("h4", string="Verify Your Phone Number")
        
        assert success_heading is not None, "Success page was not rendered for verified phone user"
        assert otp_heading is None, "OTP page should NOT render for users with already verified phones"
        
        # Check that phone shows as verified in the success page
        phone_verified_text = soup.find("p", string=lambda text: text and "Phone Number:" in text and "(Verified)" in text)
        assert phone_verified_text is not None, "Phone should show as verified in success page"
        
        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number verified"] == "TRUE", "phone number verification should remain TRUE"


def test_1_email_1_phone_verified_subscribed_display(client):
    """
    Tests that the successfully_registered.html template correctly displays phone number
    verification and subscription status for users with 1 email and 1 phone number.
    User should have phone number "+18057105809" with "TRUE" for both verified and subscribed.
    """
    
    # --- CLEAR MEMBERS SHEET --- #
    clear_members_sheet(wks)
    
    # --- GET EVENT NAME --- #
    event_name, ticket, questions, base_answer = get_event_info(client)
    
    # --- CLEAR EVENT SHEET --- #
    event_wks = clear_event_sheet(sh, event_name)
    
    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    phone_number = "+18057105809"
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
    user[wks_columns["Secondary Email"] - 1] = ""
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"  # Phone already verified
    
    wks.append_row(user)
    time.sleep(3)
    
    token = generate_token(primary_email)
    
    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore
    
    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "phone_number": "8057105809",  # Same phone number as in database
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",
        "primary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }
    
    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"
    
    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1
    
    # --- SUBMIT FORM AND CHECK FOR SUCCESS PAGE --- #
    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)
        
        soup = BeautifulSoup(response.data, "html.parser")
        
        # Should show success page
        success_heading = soup.find("p", string=f"You have successfully registered for {event_name} ")
        assert success_heading is not None, "Success page was not rendered"
        
        # Check that phone shows as verified and subscribed in the success page
        phone_verified_text = soup.find("p", string=lambda text: text and "Phone Number:" in text and "(Verified)" in text)
        phone_subscribed_text = soup.find("p", string=lambda text: text and "Phone Number:" in text and "(Subscribed)" in text)
        
        assert phone_verified_text is not None, "Phone should show as verified in success page"
        assert phone_subscribed_text is not None, "Phone should show as subscribed in success page"
        
        # Verify the phone number text contains both labels
        phone_p_tag = soup.find("p", string=lambda text: text and "Phone Number:" in text)
        assert phone_p_tag is not None, "Phone number paragraph not found"
        phone_text = phone_p_tag.get_text()
        assert "(Verified)" in phone_text, "Phone verification status not displayed correctly"
        assert "(Subscribed)" in phone_text, "Phone subscription status not displayed correctly"
        
        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number verified"] == "TRUE", "phone number verification should remain TRUE"
        assert row["Phone number subscribed"] == "TRUE", "phone number subscription should remain TRUE"


def test_2_email_1_phone_verified_subscribed_display(client):
    """
    Tests that the successfully_registered.html template correctly displays phone number
    verification and subscription status for users with 2 emails and 1 phone number.
    User should have phone number "+18057105809" with "TRUE" for both verified and subscribed.
    """
    
    # --- CLEAR MEMBERS SHEET --- #
    clear_members_sheet(wks)
    
    # --- GET EVENT NAME --- #
    event_name, ticket, questions, base_answer = get_event_info(client)
    
    # --- CLEAR EVENT SHEET --- #
    event_wks = clear_event_sheet(sh, event_name)
    
    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "test2@email.com"
    phone_number = "+18057105809"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"  # Phone already verified
    
    wks.append_row(user)
    time.sleep(3)
    
    token = generate_token(primary_email)
    
    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/event-registration/{event_name}/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore
    
    # --- BUILD FORM DATA --- #
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",  # Same phone number as in database
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "register_event": "y",
        "csrf_token": csrf_token
    }
    
    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We'll just select the first option by its index '0'.
                form_data[field.label] = '0'
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split('\n')
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"
    
    form_data["event_tickets"] = ticket
    counter = 1
    for question in questions:
        form_data["event_" + question] = base_answer + str(counter)
        counter += 1
    
    # --- SUBMIT FORM AND CHECK FOR SUCCESS PAGE --- #
    with client as c:
        response = c.post(f"membership/event-registration/{event_name}/{token}",
            data=form_data,
            follow_redirects=True)
        
        soup = BeautifulSoup(response.data, "html.parser")
        
        # Should show success page
        success_heading = soup.find("p", string=f"You have successfully registered for {event_name} ")
        assert success_heading is not None, "Success page was not rendered"
        
        # Check that phone shows as verified and subscribed in the success page
        phone_verified_text = soup.find("p", string=lambda text: text and "Phone Number:" in text and "(Verified)" in text)
        phone_subscribed_text = soup.find("p", string=lambda text: text and "Phone Number:" in text and "(Subscribed)" in text)
        
        assert phone_verified_text is not None, "Phone should show as verified in success page"
        assert phone_subscribed_text is not None, "Phone should show as subscribed in success page"
        
        # Verify the phone number text contains both labels
        phone_p_tag = soup.find("p", string=lambda text: text and "Phone Number:" in text)
        assert phone_p_tag is not None, "Phone number paragraph not found"
        phone_text = phone_p_tag.get_text()
        assert "(Verified)" in phone_text, "Phone verification status not displayed correctly"
        assert "(Subscribed)" in phone_text, "Phone subscription status not displayed correctly"
        
        # Also verify both emails are displayed correctly
        primary_email_text = soup.find("p", string=lambda text: text and "Primary Email:" in text and primary_email in text)
        secondary_email_text = soup.find("p", string=lambda text: text and "Secondary Email:" in text and secondary_email in text)
        
        assert primary_email_text is not None, "Primary email not found in success page"
        assert secondary_email_text is not None, "Secondary email not found in success page"
        
        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == secondary_email, "secondary email changed in members sheet when it should stay the same"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number verified"] == "TRUE", "phone number verification should remain TRUE"
        assert row["Phone number subscribed"] == "TRUE", "phone number subscription should remain TRUE"
        