import time
import re

from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event
from project import get_wks_columns, wks, get_wks_records, sh
from tests.testingHelpers import clear_members_sheet, get_event_info, clear_event_sheet


def test_update_bad_token(client):

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

    token = "1111"

    with client as c:
        response = c.get(f"membership/update/{token}", follow_redirects=True)
        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "ERROR 02", "ERROR 4 NOT RENDERED"


def test_happy_get(client):

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
        response = c.get(f"/membership/update/{token}")
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


def test_update_happy_post(client):

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
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"

        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "I2G Membership Updated", "THANKS UPDATE PAGE NOT RENDERED"



def update_test_primary_exists_as_nonexpired_primary(client):

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
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)
        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "ERROR 04", "ERROR 4 NOT RENDERED"



def test_update_primary_exists_as_nonexpired_secondary(client):

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
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)
        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "ERROR 04", "ERROR 4 NOT RENDERED"


def test_update_secondary_exists_as_nonexpired_primary(client):

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
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)
        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "ERROR 04", "ERROR 4 NOT RENDERED"



def test_upate_secondary_exists_as_nonexpired_secondary(client):

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


def test_update_swap_info(client):

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
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"

        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "I2G Membership Updated", "THANKS UPDATE PAGE NOT RENDERED"

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == secondary_email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == primary_email, "sec email wrong in members sheet"


def test_update_new_prim_diff_sec(client):

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
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"

        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "I2G Membership Updated", "THANKS UPDATE PAGE NOT RENDERED"

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == secondary_email2, "prim email wrong in members sheet"
        assert row["Secondary Email"] == secondary_email, "sec email wrong in members sheet"


def test_update_new_sec_same_prim(client):

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
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"

        heading = soup.find("h1")
        assert heading, "HEADING NOT FOUND"
        assert heading.get_text(strip=True) == "I2G Membership Updated", "THANKS UPDATE PAGE NOT RENDERED"

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == secondary_email2, "sec email wrong in members sheet"


def test_update_swap_2_email_to_2_email_1_phone_otp(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and changes to 2 emails and 1 phone number. Should render OTP verification form.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
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
    user[wks_columns["Phone Number"] - 1] = ""  # No phone initially
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User adds a phone number while keeping both emails
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "phone_number": "8057105809",  # Add new phone number
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
        response = c.post(f"membership/update/{token}",
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


def test_update_swap_2_email_to_2_email_1_phone_in_use(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and tries to add a phone number that's already in use by another user.
    Should render ERROR 03.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to add phone) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
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
    user[wks_columns["Phone Number"] - 1] = ""  # No phone initially
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

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
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User tries to add a phone number that's already in use by another user
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no phone was added)
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == "", "First user phone number should remain empty"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == primary_email2, "Second user primary email changed"
        assert second_user["Secondary Email"] == secondary_email2, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(taken_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to phone number conflict"


def test_update_swap_2_email_to_1_email_1_phone_otp(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and changes to 1 email and 1 phone number. Should clear secondary email and render OTP verification form.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
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
    user[wks_columns["Phone Number"] - 1] = ""  # No phone initially
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User removes secondary email and adds a phone number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": "",  # Remove secondary email
        "confirm_secondary": "",
        "phone_number": "8057105809",  # Add new phone number
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Important: include phone_subscribe
        "primary_subscribe": "y",
        "secondary_subscribe": "n",  # No secondary email anymore
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
        response = c.post(f"membership/update/{token}",
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
        assert row["Secondary Email"] == "", "secondary email not cleared in members sheet"
        assert row["Secondary Verified"] == "", "secondary verified not cleared in members sheet"
        assert row["Secondary Subscribed"] == "", "secondary subscribed not cleared in members sheet"
        assert row["Secondary Expired"] == "", "secondary expired not cleared in members sheet"
        assert row["Secondary Bounced"] == "", "secondary bounced not cleared in members sheet"
        assert row["Phone Number"] == int(new_phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number verified"] == "FALSE", "phone number verification should be FALSE for new number"


def test_update_swap_2_email_to_1_email_1_phone_in_use(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and tries to remove secondary email and add a phone number that's already in use by another user.
    Should render ERROR 03 and leave all previous data unchanged.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to add phone) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
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
    user[wks_columns["Phone Number"] - 1] = ""  # No phone initially
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

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
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User tries to remove secondary email and add a phone number that's already in use by another user
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": "",  # Remove secondary email
        "confirm_secondary": "",
        "phone_number": "8057105809",  # Trying to use phone number that belongs to second user
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Important: include phone_subscribe
        "primary_subscribe": "y",
        "secondary_subscribe": "n",  # No secondary email anymore
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed - should remain unchanged"
        assert first_user["Secondary Verified"] == "TRUE", "First user secondary verified changed - should remain unchanged"
        assert first_user["Secondary Subscribed"] == "TRUE", "First user secondary subscribed changed - should remain unchanged"
        assert first_user["Secondary Expired"] == "FALSE", "First user secondary expired changed - should remain unchanged"
        assert first_user["Secondary Bounced"] == "", "First user secondary bounced changed - should remain unchanged"
        assert first_user["Phone Number"] == "", "First user phone number should remain empty"
        assert first_user["Phone number subscribed"] == "", "First user phone subscribed should remain empty"
        assert first_user["Phone number verified"] == "", "First user phone verified should remain empty"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == primary_email2, "Second user primary email changed"
        assert second_user["Secondary Email"] == secondary_email2, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(taken_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to phone number conflict"


def test_update_swap_1_email_1_phone_to_2_email_success(client):
    """
    This tests for when a user originally registered with 1 email and 1 phone
    and changes to 2 emails (no phone). Should clear all phone data and show success page.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_phone_number = "+12345678901"
    new_secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Email"] - 1] = ""  # No secondary email initially
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number  # Has phone initially
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User adds secondary email and removes phone number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": new_secondary_email,  # Add secondary email
        "confirm_secondary": new_secondary_email,
        "phone_number": "",  # Remove phone number
        "confirm_phone_number": "",
        "country_code": "",
        "phone_subscribe": "n",  # No phone subscription
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="I2G Membership Updated")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The success page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == new_secondary_email, "secondary email not added in members sheet"
        assert row["Secondary Verified"] == "FALSE", "secondary email should be unverified initially"
        assert row["Secondary Subscribed"] == "FALSE", "secondary email should be unsubscribed initially"
        assert row["Secondary Expired"] == "FALSE", "secondary expired should be FALSE"
        assert row["Secondary Bounced"] == "", "secondary bounced should be empty"
        # Verify all phone data is cleared
        assert row["Phone Number"] == "", "phone number not cleared in members sheet"
        assert row["Phone number subscribed"] == "", "phone number subscribed not cleared in members sheet"
        assert row["Phone number verified"] == "", "phone number verified not cleared in members sheet"


def test_update_swap_1_email_1_phone_to_2_email_1_phone_same_phone_success(client):
    """
    This tests for when a user originally registered with 1 email and 1 phone
    and changes to 2 emails and keeps the same phone number. Should show success page.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    phone_number = "+12345678901"
    new_secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Email"] - 1] = ""  # No secondary email initially
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number  # Has phone initially
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User adds secondary email and keeps the same phone number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": new_secondary_email,  # Add secondary email
        "confirm_secondary": new_secondary_email,
        "phone_number": "2345678901",  # Keep same phone number (without country code)
        "confirm_phone_number": "2345678901",
        "country_code": "+1",
        "phone_subscribe": "y",  # Keep phone subscription
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="I2G Membership Updated")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The success page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == new_secondary_email, "secondary email not added in members sheet"
        assert row["Secondary Verified"] == "FALSE", "secondary email should be unverified initially"
        assert row["Secondary Subscribed"] == "FALSE", "secondary email should be unsubscribed initially"
        assert row["Secondary Expired"] == "FALSE", "secondary expired should be FALSE"
        assert row["Secondary Bounced"] == "", "secondary bounced should be empty"
        # Verify phone data remains the same
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in members sheet when it should stay the same"
        assert row["Phone number subscribed"] == "TRUE", "phone number subscribed changed in members sheet"
        assert row["Phone number verified"] == "TRUE", "phone number verified changed in members sheet"


def test_update_swap_1_email_1_phone_to_2_email_1_phone_different_phone_otp(client):
    """
    This tests for when a user originally registered with 1 email and 1 phone
    and changes to 2 emails and a different phone number. Should render OTP verification form.
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
    new_secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Email"] - 1] = ""  # No secondary email initially
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number  # Has phone initially
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User adds secondary email and changes to a different phone number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": new_secondary_email,  # Add secondary email
        "confirm_secondary": new_secondary_email,
        "phone_number": "8057105809",  # Change to different phone number (without country code)
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Keep phone subscription
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
        response = c.post(f"membership/update/{token}",
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
        assert row["Secondary Email"] == new_secondary_email, "secondary email not added in members sheet"
        assert row["Secondary Verified"] == "FALSE", "secondary email should be unverified initially"
        assert row["Secondary Subscribed"] == "FALSE", "secondary email should be unsubscribed initially"
        assert row["Secondary Expired"] == "FALSE", "secondary expired should be FALSE"
        assert row["Secondary Bounced"] == "", "secondary bounced should be empty"
        # Verify phone data is updated but verification is FALSE
        assert row["Phone Number"] == int(new_phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number subscribed"] == "TRUE", "phone number subscribed changed in members sheet"
        assert row["Phone number verified"] == "FALSE", "phone number verification should be FALSE for new number"


def test_update_swap_1_email_1_phone_to_2_email_1_phone_different_phone_in_use(client):
    """
    This tests for when a user originally registered with 1 email and 1 phone
    and tries to add a secondary email and change to a phone number that's already in use by another user.
    Should render ERROR 03.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change phone) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_phone_number = "+12345678901"
    new_secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Email"] - 1] = ""  # No secondary email initially
    user[wks_columns["Secondary Verified"] - 1] = ""
    user[wks_columns["Secondary Subscribed"] - 1] = ""
    user[wks_columns["Secondary Expired"] - 1] = ""
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number  # Has phone initially
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
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User tries to add secondary email and change to a phone number that's already in use by another user
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": new_secondary_email,  # Add secondary email
        "confirm_secondary": new_secondary_email,
        "phone_number": "8057105809",  # Trying to use phone number that belongs to second user
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Keep phone subscription
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == "", "First user secondary email should remain empty"
        assert first_user["Secondary Verified"] == "", "First user secondary verified should remain empty"
        assert first_user["Secondary Subscribed"] == "", "First user secondary subscribed should remain empty"
        assert first_user["Secondary Expired"] == "", "First user secondary expired should remain empty"
        assert first_user["Secondary Bounced"] == "", "First user secondary bounced should remain empty"
        assert first_user["Phone Number"] == int(old_phone_number[1:]), "First user phone number should remain unchanged"
        assert first_user["Phone number subscribed"] == "TRUE", "First user phone subscribed should remain unchanged"
        assert first_user["Phone number verified"] == "TRUE", "First user phone verified should remain unchanged"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == primary_email2, "Second user primary email changed"
        assert second_user["Secondary Email"] == secondary_email2, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(taken_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to phone number conflict"


def test_update_swap_2_email_1_phone_to_2_email_success(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and changes to 2 emails (no phone). Should clear all phone data and show success page.
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
    user[wks_columns["Secondary Email"] - 1] = secondary_email  # Has secondary email initially
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number  # Has phone initially
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User keeps both emails and removes phone number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "phone_number": "",  # Remove phone number
        "confirm_phone_number": "",
        "country_code": "",
        "phone_subscribe": "n",  # No phone subscription
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="I2G Membership Updated")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The success page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == secondary_email, "secondary email changed in members sheet when it should stay the same"
        # Verify all phone data is cleared
        assert row["Phone Number"] == "", "phone number not cleared in members sheet"
        assert row["Phone number subscribed"] == "", "Phone number subscribe field not cleared in members sheet"
        assert row["Phone number verified"] == "", "Phone number verified field not cleared in members sheet"

        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email wrong in event sheet"
        assert row["Membership Secondary"] == secondary_email, "Secondary email wrong in event sheet"
        assert row["Phone Number"] == "", "phone number not cleared in events sheet"


def test_update_swap_2_email_1_phone_to_1_email_1_phone_same_number_success(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and changes to 1 email and keeps the same phone number. Should clear secondary email data and show success page.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
    phone_number = "+12345678901"
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
    user[wks_columns["Secondary Email"] - 1] = secondary_email  # Has secondary email initially
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number  # Has phone initially
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User keeps primary email and phone, removes secondary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": "",  # Remove secondary email
        "confirm_secondary": "",
        "phone_number": "2345678901",  # Keep same phone number (without country code)
        "confirm_phone_number": "2345678901",
        "country_code": "+1",
        "phone_subscribe": "y",  # Keep phone subscription
        "primary_subscribe": "y",
        "secondary_subscribe": "n",  # No secondary email subscription
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="I2G Membership Updated")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The success page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        # Verify all secondary email data is cleared
        assert row["Secondary Email"] == "", "secondary email not cleared in members sheet"
        assert row["Secondary Verified"] == "", "secondary verified not cleared in members sheet"
        assert row["Secondary Subscribed"] == "", "secondary subscribed not cleared in members sheet"
        assert row["Secondary Expired"] == "", "secondary expired not cleared in members sheet"
        assert row["Secondary Bounced"] == "", "secondary bounced not cleared in members sheet"
        # Verify phone data remains the same
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in members sheet when it should stay the same"
        assert row["Phone number subscribed"] == "TRUE", "phone number subscribed changed in members sheet"
        assert row["Phone number verified"] == "TRUE", "phone number verified changed in members sheet"

        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email wrong in event sheet"
        assert row["Membership Secondary"] == "", "Secondary email not cleared in event sheet"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number wrong in events sheet"


def test_update_swap_2_email_1_phone_to_1_email_1_phone_new_number_otp(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and changes to 1 email and a new phone number. Should clear secondary email data and render OTP verification form.
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
    user[wks_columns["Secondary Email"] - 1] = secondary_email  # Has secondary email initially
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number  # Has phone initially
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User keeps primary email, removes secondary email, and changes to new phone number
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": "",  # Remove secondary email
        "confirm_secondary": "",
        "phone_number": "8057105809",  # Change to new phone number (without country code)
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Keep phone subscription
        "primary_subscribe": "y",
        "secondary_subscribe": "n",  # No secondary email subscription
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
        response = c.post(f"membership/update/{token}",
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
        # Verify all secondary email data is cleared
        assert row["Secondary Email"] == "", "secondary email not cleared in members sheet"
        assert row["Secondary Verified"] == "", "secondary verified not cleared in members sheet"
        assert row["Secondary Subscribed"] == "", "secondary subscribed not cleared in members sheet"
        assert row["Secondary Expired"] == "", "secondary expired not cleared in members sheet"
        assert row["Secondary Bounced"] == "", "secondary bounced not cleared in members sheet"
        # Verify phone data is updated but verification is FALSE
        assert row["Phone Number"] == int(new_phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number subscribed"] == "TRUE", "phone number subscribed changed in members sheet"
        assert row["Phone number verified"] == "FALSE", "phone number verification should be FALSE for new number"


def test_update_swap_2_email_1_phone_to_1_email_1_phone_new_number_in_use(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and tries to remove secondary email and change to a phone number that's already in use by another user.
    Should render ERROR 03 and leave all previous data unchanged.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change phone) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
    old_phone_number = "+12345678901"
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
    user[wks_columns["Secondary Email"] - 1] = secondary_email  # Has secondary email initially
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = old_phone_number  # Has phone initially
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
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User tries to remove secondary email and change to a phone number that's already in use by another user
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": primary_email,  # Keep same primary email
        "confirm_primary": primary_email,
        "secondary_email": "",  # Remove secondary email
        "confirm_secondary": "",
        "phone_number": "8057105809",  # Trying to use phone number that belongs to second user
        "confirm_phone_number": "8057105809",
        "country_code": "+1",
        "phone_subscribe": "y",  # Keep phone subscription
        "primary_subscribe": "y",
        "secondary_subscribe": "n",  # No secondary email subscription
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 03")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed - should remain unchanged"
        assert first_user["Secondary Verified"] == "TRUE", "First user secondary verified changed - should remain unchanged"
        assert first_user["Secondary Subscribed"] == "TRUE", "First user secondary subscribed changed - should remain unchanged"
        assert first_user["Secondary Expired"] == "FALSE", "First user secondary expired changed - should remain unchanged"
        assert first_user["Secondary Bounced"] == "", "First user secondary bounced changed - should remain unchanged"
        assert first_user["Phone Number"] == int(old_phone_number[1:]), "First user phone number should remain unchanged"
        assert first_user["Phone number subscribed"] == "TRUE", "First user phone subscribed should remain unchanged"
        assert first_user["Phone number verified"] == "TRUE", "First user phone verified should remain unchanged"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == primary_email2, "Second user primary email changed"
        assert second_user["Secondary Email"] == secondary_email2, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(taken_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to phone number conflict"


def test_update_swap_2_email_1_phone_change_primary_email_success(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
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
    secondary_email = "secondary@email.com"
    phone_number = "+12345678901"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(old_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
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
        "phone_number": "2345678901",  # Keep same phone number (without country code)
        "confirm_phone_number": "2345678901",
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

    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="I2G Membership Updated")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The success page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == new_primary_email, "primary email not updated in members sheet"
        assert row["Secondary Email"] == secondary_email, "secondary email changed in members sheet when it should stay the same"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in members sheet when it should stay the same"

        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == new_primary_email, "Primary email not updated in event sheet"
        assert row["Membership Secondary"] == secondary_email, "Secondary email changed in event sheet when it should stay the same"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in events sheet when it should stay the same"


def test_update_swap_2_email_1_phone_change_primary_email_to_existing_primary(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and tries to change their primary email to one that's already in use as another user's primary email.
    Should render ERROR 04.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change primary email) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
    phone_number = "+12345678901"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the primary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    taken_primary_email = "taken@email.com"  # This is the primary email first user will try to use
    other_secondary_email = "othersecondary@email.com"
    other_phone_number = "+19876543210"
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
    user2[wks_columns["Secondary Email"] - 1] = other_secondary_email
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = other_phone_number
    user2[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user2[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User tries to change primary email to one already in use as another user's primary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": taken_primary_email,  # Trying to use primary email that belongs to second user
        "confirm_primary": taken_primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "phone_number": "2345678901",  # Keep same phone number (without country code)
        "confirm_phone_number": "2345678901",
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

    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == original_primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == int(phone_number[1:]), "First user phone number changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == taken_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == other_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(other_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_update_swap_2_email_1_phone_change_primary_email_to_existing_secondary(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and tries to change their primary email to one that's already in use as another user's secondary email.
    Should render ERROR 04.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change primary email) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
    phone_number = "+12345678901"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the secondary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    other_primary_email = "other@email.com"
    taken_secondary_email = "takensecondary@email.com"  # This is the secondary email first user will try to use as primary
    other_phone_number = "+19876543210"
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
    user2[wks_columns["Secondary Email"] - 1] = taken_secondary_email  # This is what user 1 wants as primary
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = other_phone_number
    user2[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user2[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User tries to change primary email to one already in use as another user's secondary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": taken_secondary_email,  # Trying to use secondary email that belongs to second user
        "confirm_primary": taken_secondary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
        "phone_number": "2345678901",  # Keep same phone number (without country code)
        "confirm_phone_number": "2345678901",
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

    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == original_primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == int(phone_number[1:]), "First user phone number changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == other_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == taken_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(other_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_update_swap_2_email_1_phone_change_secondary_email_success(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and changes their secondary email to a new email that's not in use. Should succeed.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD ROW OF DATA TO MEMBERS SHEET --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    old_secondary_email = "secondary@email.com"
    new_secondary_email = "newsecondary@email.com"
    phone_number = "+12345678901"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
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
        response = c.get(f"membership/update/{token}")
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
        "phone_number": "2345678901",  # Keep same phone number (without country code)
        "confirm_phone_number": "2345678901",
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

    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="I2G Membership Updated")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The success page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        row = records[0]
        assert row["Primary Email"] == primary_email, "primary email changed in members sheet when it should stay the same"
        assert row["Secondary Email"] == new_secondary_email, "secondary email not updated in members sheet"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in members sheet when it should stay the same"

        event_records = get_wks_records(event_wks)
        row = event_records[0]
        assert row["Membership Primary"] == primary_email, "Primary email changed in event sheet when it should stay the same"
        assert row["Membership Secondary"] == new_secondary_email, "Secondary email not updated in event sheet"
        assert row["Phone Number"] == int(phone_number[1:]), "phone number changed in events sheet when it should stay the same"


def test_update_swap_2_email_1_phone_change_secondary_email_to_existing_primary(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and tries to change their secondary email to one that's already in use as another user's primary email.
    Should render ERROR 04.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change secondary email) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    original_secondary_email = "secondary@email.com"
    phone_number = "+12345678901"
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
    user[wks_columns["Secondary Email"] - 1] = original_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the primary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    taken_primary_email = "takenprimary@email.com"  # This is the primary email first user will try to use as secondary
    other_secondary_email = "othersecondary@email.com"
    other_phone_number = "+19876543210"
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = taken_primary_email  # This is what user 1 wants as secondary
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = other_secondary_email
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = other_phone_number
    user2[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user2[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
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
        "secondary_email": taken_primary_email,  # Trying to use primary email that belongs to second user
        "confirm_secondary": taken_primary_email,
        "phone_number": "2345678901",  # Keep same phone number (without country code)
        "confirm_phone_number": "2345678901",
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

    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == original_secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == int(phone_number[1:]), "First user phone number changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == taken_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == other_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(other_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_update_swap_2_email_1_phone_change_secondary_email_to_existing_secondary(client):
    """
    This tests for when a user originally registered with 2 emails and 1 phone
    and tries to change their secondary email to one that's already in use as another user's secondary email.
    Should render ERROR 04.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change secondary email) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    original_secondary_email = "secondary@email.com"
    phone_number = "+12345678901"
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
    user[wks_columns["Secondary Email"] - 1] = original_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = phone_number
    user[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the secondary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    other_primary_email = "other@email.com"
    taken_secondary_email = "takensecondary@email.com"  # This is the secondary email first user will try to use
    other_phone_number = "+19876543210"
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
    user2[wks_columns["Secondary Email"] - 1] = taken_secondary_email  # This is what user 1 wants as secondary
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = other_phone_number
    user2[wks_columns["Phone number subscribed"] - 1] = "TRUE"
    user2[wks_columns["Phone number verified"] - 1] = "TRUE"

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
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
        "secondary_email": taken_secondary_email,  # Trying to use secondary email that belongs to second user
        "confirm_secondary": taken_secondary_email,
        "phone_number": "2345678901",  # Keep same phone number (without country code)
        "confirm_phone_number": "2345678901",
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

    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == original_secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == int(phone_number[1:]), "First user phone number changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == other_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == taken_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == int(other_phone_number[1:]), "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_update_swap_2_email_change_primary_email_success(client):
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
    secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""  # No phone
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(old_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="I2G Membership Updated")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The success page was not rendered. The update may have failed."

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


def test_update_swap_2_email_change_primary_email_to_existing_primary(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and tries to change their primary email to one that's already in use as another user's primary email.
    Should render ERROR 04.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change primary email) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""  # No phone
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the primary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    taken_primary_email = "taken@email.com"  # This is the primary email first user will try to use
    other_secondary_email = "othersecondary@email.com"
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
    user2[wks_columns["Secondary Email"] - 1] = other_secondary_email
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""  # No phone
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User tries to change primary email to one already in use as another user's primary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": taken_primary_email,  # Trying to use primary email that belongs to second user
        "confirm_primary": taken_primary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == original_primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == "", "First user phone number changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == taken_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == other_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_update_swap_2_email_change_primary_email_to_existing_secondary(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and tries to change their primary email to one that's already in use as another user's secondary email.
    Should render ERROR 04.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change primary email) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    original_primary_email = "test@email.com"
    secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""  # No phone
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the secondary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    other_primary_email = "other@email.com"
    taken_secondary_email = "takensecondary@email.com"  # This is the secondary email first user will try to use as primary
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
    user2[wks_columns["Secondary Email"] - 1] = taken_secondary_email  # This is what user 1 wants as primary
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""  # No phone
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(original_primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"] # type: ignore

    # --- BUILD FORM DATA --- #
    # User tries to change primary email to one already in use as another user's secondary email
    form_data = {
        "first_name": first_name,
        "last_name": last_name,
        "primary_email": taken_secondary_email,  # Trying to use secondary email that belongs to second user
        "confirm_primary": taken_secondary_email,
        "secondary_email": secondary_email,  # Keep same secondary email
        "confirm_secondary": secondary_email,
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == original_primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == "", "First user phone number changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == other_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == taken_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_update_swap_2_email_change_secondary_email_success(client):
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
    old_secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""  # No phone
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="I2G Membership Updated")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The success page was not rendered. The update may have failed."

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


def test_update_swap_2_email_change_secondary_email_to_existing_primary(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and tries to change their secondary email to one that's already in use as another user's primary email.
    Should render ERROR 04.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change secondary email) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    original_secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Email"] - 1] = original_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""  # No phone
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the primary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    taken_primary_email = "takenprimary@email.com"  # This is the primary email first user will try to use as secondary
    other_secondary_email = "othersecondary@email.com"
    first_name2 = "SECOND USER FIRST"
    last_name2 = "SECOND USER LAST"
    start2 = "SECOND START"
    update2 = "SECOND UPDATE"

    user2[wks_columns["Order"] - 1] = "2"
    user2[wks_columns["First Name"] - 1] = first_name2
    user2[wks_columns["Last Name"] - 1] = last_name2
    user2[wks_columns["When Started"] - 1] = start2
    user2[wks_columns["Last Updated"] - 1] = update2
    user2[wks_columns["Primary Email"] - 1] = taken_primary_email  # This is what user 1 wants as secondary
    user2[wks_columns["Primary Verified"] - 1] = "TRUE"
    user2[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Primary Expired"] - 1] = "FALSE"
    user2[wks_columns["Primary Bounced"] - 1] = ""
    user2[wks_columns["Secondary Email"] - 1] = other_secondary_email
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""  # No phone
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
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
        "secondary_email": taken_primary_email,  # Trying to use primary email that belongs to second user
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == original_secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == "", "First user phone number changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == taken_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == other_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"


def test_update_swap_2_email_change_secondary_email_to_existing_secondary(client):
    """
    This tests for when a user originally registered with 2 emails (no phone)
    and tries to change their secondary email to one that's already in use as another user's secondary email.
    Should render ERROR 04.
    """

    clear_members_sheet(wks)

    event_name, ticket, questions, base_answer = get_event_info(client)

    event_wks = clear_event_sheet(sh, event_name)

    # --- ADD FIRST USER TO MEMBERS SHEET (the one who will try to change secondary email) --- #
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    primary_email = "test@email.com"
    original_secondary_email = "secondary@email.com"
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
    user[wks_columns["Secondary Email"] - 1] = original_secondary_email
    user[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = ""  # No phone
    user[wks_columns["Phone number subscribed"] - 1] = ""
    user[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user)

    # --- ADD SECOND USER TO MEMBERS SHEET (who owns the secondary email the first user wants) --- #
    user2 = ["" for i in range(len(wks_columns))]
    other_primary_email = "other@email.com"
    taken_secondary_email = "takensecondary@email.com"  # This is the secondary email first user will try to use
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
    user2[wks_columns["Secondary Email"] - 1] = taken_secondary_email  # This is what user 1 wants as secondary
    user2[wks_columns["Secondary Verified"] - 1] = "TRUE"
    user2[wks_columns["Secondary Subscribed"] - 1] = "TRUE"
    user2[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user2[wks_columns["Secondary Bounced"] - 1] = ""
    user2[wks_columns["Info Completed"] - 1] = "TRUE"
    user2[wks_columns["Phone Number"] - 1] = ""  # No phone
    user2[wks_columns["Phone number subscribed"] - 1] = ""
    user2[wks_columns["Phone number verified"] - 1] = ""

    wks.append_row(user2)
    time.sleep(3)

    token = generate_token(primary_email)

    # --- GET CSRF TOKEN --- #
    with client as c:
        response = c.get(f"membership/update/{token}")
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
        "secondary_email": taken_secondary_email,  # Trying to use secondary email that belongs to second user
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
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 04")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The update may have failed."

        time.sleep(2)
        records = get_wks_records(wks)
        assert len(records) == 2, "Number of users changed unexpectedly"
        
        # Verify first user data is unchanged (no changes should have occurred)
        first_user = records[0]
        assert first_user["Primary Email"] == primary_email, "First user primary email changed"
        assert first_user["Secondary Email"] == original_secondary_email, "First user secondary email changed"
        assert first_user["Phone Number"] == "", "First user phone number changed"
        
        # Verify second user data is unchanged
        second_user = records[1]
        assert second_user["Primary Email"] == other_primary_email, "Second user primary email changed"
        assert second_user["Secondary Email"] == taken_secondary_email, "Second user secondary email changed"
        assert second_user["Phone Number"] == "", "Second user phone number changed"

        # Verify no event registration was created
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "Event registration should not have been created due to email conflict"



def test_update_otp_form_renders_for_unverified_phone(client):
    """
    Tests that the OTP form renders when a user updates their info with an unverified phone number.
    User should have phone number "+18057105809" with "FALSE" for phone number verified.
    """
    
    # --- CLEAR MEMBERS SHEET --- #
    clear_members_sheet(wks)
    
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
        response = c.get(f"membership/update/{token}")
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
        "csrf_token": csrf_token
    }
    
    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We will just select the first option by its index "0".
                form_data[field.label] = "0"
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split("\n")
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"
    
    # --- SUBMIT FORM AND CHECK FOR OTP PAGE --- #
    with client as c:
        response = c.post(f"membership/update/{token}",
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
        assert row["Phone Number"] == int(phone_number[1:]), "phone number not updated in members sheet"
        assert row["Phone number verified"] == "FALSE", "phone number verification should remain FALSE"


def test_update_verified_phone_no_otp_required(client):
    """
    Tests that users with already verified phone numbers do NOT get redirected to OTP verification during update.
    User should have phone number "+18057105809" with "TRUE" for phone number verified.
    """
    
    # --- CLEAR MEMBERS SHEET --- #
    clear_members_sheet(wks)
    
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
        response = c.get(f"membership/update/{token}")
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
        "csrf_token": csrf_token
    }
    
    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We will just select the first option by its index "0".
                form_data[field.label] = "0"
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split("\n")
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"
    
    # --- SUBMIT FORM AND CHECK FOR SUCCESS PAGE (NOT OTP) --- #
    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)
        
        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)
        
        # Should show success page, NOT OTP page
        success_heading = soup.find("h1", string="I2G Membership Updated")
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


def test_update_1_email_1_phone_verified_subscribed_display(client):
    """
    Tests that the thanks_update.html template correctly displays phone number
    verification and subscription status for users with 1 email and 1 phone number during update.
    User should have phone number "+18057105809" with "TRUE" for both verified and subscribed.
    """
    
    # --- CLEAR MEMBERS SHEET --- #
    clear_members_sheet(wks)
    
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
        response = c.get(f"membership/update/{token}")
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
        "csrf_token": csrf_token
    }
    
    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We will just select the first option by its index "0".
                form_data[field.label] = "0"
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split("\n")
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"
    
    # --- SUBMIT FORM AND CHECK FOR SUCCESS PAGE --- #
    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)
        
        soup = BeautifulSoup(response.data, "html.parser")
        
        # Should show success page
        success_heading = soup.find("h1", string="I2G Membership Updated")
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


def test_update_2_email_1_phone_verified_subscribed_display(client):
    """
    Tests that the thanks_update.html template correctly displays phone number
    verification and subscription status for users with 2 emails and 1 phone number during update.
    User should have phone number "+18057105809" with "TRUE" for both verified and subscribed.
    """
    
    # --- CLEAR MEMBERS SHEET --- #
    clear_members_sheet(wks)
    
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
        response = c.get(f"membership/update/{token}")
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
        "csrf_token": csrf_token
    }
    
    with client.application.app_context():
        required_fields = edit_form.query.filter_by(required=True).all()
        for field in required_fields:
            # Provide dummy data for dynamically generated required fields.
            if field.field_type == "Checkbox":
                # For checkboxes, WTForms expects a list of values.
                # We will just select the first option by its index "0".
                form_data[field.label] = "0"
            elif field.field_type == "Radio":
                # For radio buttons, we provide the value of the choice.
                options = field.options.split("\n")
                if options:
                    form_data[field.label] = options[0]
            else: # For StringField, TextAreaField, etc.
                form_data[field.label] = f"Test data for {field.label}"
    
    # --- SUBMIT FORM AND CHECK FOR SUCCESS PAGE --- #
    with client as c:
        response = c.post(f"membership/update/{token}",
            data=form_data,
            follow_redirects=True)
        
        soup = BeautifulSoup(response.data, "html.parser")
        
        # Should show success page
        success_heading = soup.find("h1", string="I2G Membership Updated")
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
        