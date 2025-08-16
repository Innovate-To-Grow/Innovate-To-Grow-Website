import time
import re

from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event
from project import get_wks_columns, wks, get_wks_records, sh

def test_no_user_found(client):
    """
        Tests if error2.html renders if "membership/event-registration/<event_name>/<token>"
        API call is sent and there is no matching user with the email in the members sheet
    """


    # --- CLEAR MEMBERS SHEET --- #
    records = get_wks_records(wks)
    print("records:")
    print(records)
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
    assert event_row["Membership Primary"] == primary_email, "PRIMARY EMAIL NOT UPDATED IN SET UP"
    assert event_row["Membership Secondary"] == secondary_email, "SECONDARY EMAIL NOT UPDATED IN SET UP"
    assert event_row["First Name"] == first_name, "FIRST NAME NOT UPDATED IN SET UP"
    assert event_row["Last Name"] == last_name, "LAST NAME NOT UPDATED IN SET UP"
    assert event_row["When Started"] == start, "WHEN STARTED NOT UPDATED IN SET UP"
    assert event_row["Last Updated"] == update, "WHEN UPDATED NOT UPDATED IN SET UP"
    assert event_row["Ticket Type"] == ticket, "TICKET NOT UPDATED IN SET UP"

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



def test_primary_exists_as_non_expired_primary(client):

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
    secondary_email2 = "test3@email.com"
    first_name = "TEST FIRST NAME"
    first_name2 = "TEST2 FIRST NAME"
    last_name2 = "TEST2 LAST NAME"
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

    user[wks_columns["Order"] - 1] = "2"
    user[wks_columns["First Name"] - 1] = first_name2
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = primary_email
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
    wks.append_row(user)


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
        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "ERROR 04", "ERROR 4 NOT RENDERED"


def test_primary_exists_as_non_expired_secondary(client):

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
        assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"


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
    last_name2 = "TEST2 LAST NAME"
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

    user[wks_columns["Order"] - 1] = "2"
    user[wks_columns["First Name"] - 1] = first_name2
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = secondary_email2
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = primary_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)


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
        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "ERROR 04", "ERROR 4 NOT RENDERED"


def test_secondary_exists_as_non_expired_primary(client):

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
        assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"


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
    user[wks_columns["Primary Email"] - 1] = secondary_email
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
    wks.append_row(user)

    time.sleep(3)
    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == secondary_email
    assert row["Secondary Email"] == secondary_email2

    user[wks_columns["Order"] - 1] = "2"
    user[wks_columns["First Name"] - 1] = first_name2
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
        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "ERROR 04", "ERROR 4 NOT RENDERED"



def test_secondary_exists_as_nonexpired_secondary(client):

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
        assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"


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

    user[wks_columns["Order"] - 1] = "2"
    user[wks_columns["First Name"] - 1] = first_name2
    user[wks_columns["Last Name"] - 1] = last_name
    user[wks_columns["When Started"] - 1] = start
    user[wks_columns["Last Updated"] - 1] = update
    user[wks_columns["Primary Email"] - 1] = secondary_email2
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


    token = generate_token(secondary_email2)

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
        "primary_email": secondary_email2,
        "confirm_primary": secondary_email2,
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
        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "ERROR 04", "ERROR 4 NOT RENDERED"


def test_swap_info(client):

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
        assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"


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


def test_new_prim_same_sec(client):

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
        assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"

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
        "primary_email": secondary_email2,
        "confirm_primary": secondary_email2,
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
        assert row["Primary Email"] == secondary_email2, "prim email wrong in members sheet"
        assert row["Secondary Email"] == secondary_email, "sec email wrong in members sheet"


def test_new_sec_same_prim(client):

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
        assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"

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


def test_bad_token(client):

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
        assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"

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
