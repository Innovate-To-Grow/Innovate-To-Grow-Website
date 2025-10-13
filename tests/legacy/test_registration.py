import time
from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event
from project import get_wks_columns, wks, get_wks_records, sh

def test_post_happy_path_with_event(client):
    """
        This function tests for a new full-registration including the event registration.
        It clears the members and event sheets, gets the csrf token, creates form data,
        sends a post request, and verifies that the form data that was submitted is
        populated in the google sheet.
    """
    email = "avashraj328@gmail.com"
    token = generate_token(email)

    # Clear existing records in members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records)
    elif num_records > 0:
        wks.delete_rows(2)


    # Get the event name and clear the event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        if len(event_records) > 0:
            event_wks.delete_rows(2)
            time.sleep(3)

    csrf_token = ""

    # get CSRF token for form
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "bro@bro.com",
                "confirm_secondary": "bro@bro.com",
                "country_code": "",  
                "register_event": "y",
                "csrf_token": csrf_token,
            }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"


    # Send POST form data
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)

        # Check if the receipt page was rendered by looking for its heading.
        heading = soup.find("h1", string="I2G Membership Completed")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(3)
        # asserting members fields
        records = get_wks_records(wks)
        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == "bro@bro.com", "sec email wrong in members sheet"

        # asserting event fields
        event_records = get_wks_records(event_wks)
        event_row = event_records[0]
        assert event_row["First Name"] == "AVASH_TEST", "first name wrong in event sheet"
        assert event_row["Last Name"] == "ADHIKARI_TEST", "last name wrong in event sheet"
        assert event_row["Membership Primary"] == email, "prim email wrong in event sheet"
        assert event_row["Membership Secondary"] == "bro@bro.com", "sec email wrong in event sheet"
        assert event_row["Ticket Type"] == form_data["event_tickets"]

def test_happy_path_without_event(client):
    """
        This function tests for a new /full-registration/<token> POST request without event registration.
        It clears the members sehet, gets the event name, clears event sheet, gets the csrf token, builds
        the form, sends the POST request, verifies that the submitted info matches the google sheet and
        that the event sheet stays empty
    """

    email = "avashraj328@gmail.com"
    token = generate_token(email)

    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records)
    elif num_records > 0:
        wks.delete_rows(2)


    # Get event name and clear events sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
            event_wks.delete_rows(2)



    # get CSRF token for form
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "bro@bro.com",
                "confirm_secondary": "bro@bro.com",
                "country_code": "",  
                "csrf_token": csrf_token
            }

    # add info fields to form data
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

    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Check if the receipt page was rendered by looking for its heading.
        heading = soup.find("h1", string="I2G Membership Completed")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(3)
        # asserting members fields
        records = get_wks_records(wks)
        event_records = get_wks_records(event_wks)

        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == "bro@bro.com", "sec email wrong in members sheet"

        assert len(event_records) == 0, "event records has stuff in it"

def test_primary_email_already_exists(client):
    """
        Tests /full-registration/<token> route including event registration when we
        use a primary email that already exists
        should return error 1 template
    """

    # delete old test stuff
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records)
    elif num_records > 0:
        wks.delete_rows(2)

    # add email for this test
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    email = "test@email.com"
    sec_email = "test2@email.com"
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = "second@email.com"
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == email

    token = generate_token(email)

    with client as c:
            response = c.get(f"/membership/full-registration/{token}")
            soup = BeautifulSoup(response.data, "html.parser")
            heading = soup.find("h1", string="ERROR 01")
            assert heading is not None, "did not render error1 template"


def test_secondary_already_exists(client):
    """
        Tests /full-registration/<token> route including event registration when we
        use a secondary email that already exists
        should return error 1 template
    """

    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records)
    elif num_records > 0:
        wks.delete_rows(2)

    # add email for this test
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    sec_email = "test2@email.com"
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = "email@email.com"
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = sec_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    records = get_wks_records(wks)
    row = records[0]
    assert row["Secondary Email"] == sec_email

    token = generate_token(sec_email)

    with client as c:
            response = c.get(f"/membership/full-registration/{token}")
            soup = BeautifulSoup(response.data, "html.parser")
            heading = soup.find("h1", string="ERROR 01")
            assert heading is not None, "did not render error1 template"

def test_secondary_exists_as_expired_primary(client):
    """
        Test when a user submits a secondary email that already exists as someone elses
        primary but it is expired.
        Clears members sheet, enters row into members sheet that has an expired primary email,
        builds form, gets event name, clears event sheet, sends post request, makes sure that
        members and event sheet are updated properly
    """

    # clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    print(f"len records: {num_records}")
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
        print("boo")
    elif num_records > 0:
        print("goo")
        wks.delete_rows(2)

    time.sleep(2)

    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    email = "email@email.com"
    new_prim_email = "email2@email.com"
    sec_email = "test2@email.com"
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "TRUE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = sec_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == email, "set up for test failed"


    token = generate_token(new_prim_email)

    with client.application.app_context():
            event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    csrf_token = ""

    # get CSRF token for form
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    form_data = {
                    "first_name": "AVASH_TEST",
                    "last_name": "ADHIKARI_TEST",
                    "primary_email": new_prim_email,
                    "confirm_primary": new_prim_email,
                    "secondary_email": email,
                    "confirm_secondary": email,
                    "register_event": "y",
                    "country_code": "",  
                    "csrf_token": csrf_token
                }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"


    # Send POST form data
    with client as c:
        token = generate_token(new_prim_email)
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Check if the receipt page was rendered by looking for its heading.
        heading = soup.find("h1", string="I2G Membership Completed")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(3)
        # asserting members fields
        records = get_wks_records(wks)
        row = records[1]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == new_prim_email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == email, "sec email wrong in members sheet"

        # asserting event fields
        event_records = get_wks_records(event_wks)
        event_row = event_records[0]
        assert event_row["First Name"] == "AVASH_TEST", "first name wrong in event sheet"
        assert event_row["Last Name"] == "ADHIKARI_TEST", "last name wrong in event sheet"
        assert event_row["Membership Primary"] == new_prim_email, "prim email wrong in event sheet"
        assert event_row["Membership Secondary"] == email, "sec email wrong in event sheet"
        assert event_row["Ticket Type"] == form_data["event_tickets"]

def test_secondary_exists_as_expired_secondary(client):
    """
            Test when a user submits a secondary email that already exists as someone elses
            secondary but it is expired
            Clears members sheet, insert row with expired secondary, get event name, clear
            event sheet, get csrf token, build form data, send POST request, make sure
            events and members sheets are updated properly

    """

    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Insert row for test
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    email = "email@email.com"
    sec_email = "test2@email.com"
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = "vro@vro.com"
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = sec_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "TRUE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    records = get_wks_records(wks)
    row = records[0]
    assert row["Secondary Email"] == sec_email, "set up for test failed"


    token = generate_token(email)

    # get event name
    with client.application.app_context():
            event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    csrf_token = ""

    # get CSRF token for form
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    form_data = {
                    "first_name": "AVASH_TEST",
                    "last_name": "ADHIKARI_TEST",
                    "primary_email": email,
                    "confirm_primary": email,
                    "secondary_email": sec_email,
                    "confirm_secondary": sec_email,
                    "country_code": "",  
                    "register_event": "y",
                    "csrf_token": csrf_token
                }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"


    # Send POST form data
    with client as c:
        token = generate_token(email)
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Check if the receipt page was rendered by looking for its heading.
        heading = soup.find("h1", string="I2G Membership Completed")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        time.sleep(3)
        # asserting members fields
        records = get_wks_records(wks)
        row = records[1]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == sec_email, "sec email wrong in members sheet"

        # asserting event fields
        event_records = get_wks_records(event_wks)
        event_row = event_records[0]
        assert event_row["First Name"] == "AVASH_TEST", "first name wrong in event sheet"
        assert event_row["Last Name"] == "ADHIKARI_TEST", "last name wrong in event sheet"
        assert event_row["Membership Primary"] == email, "prim email wrong in event sheet"
        assert event_row["Membership Secondary"] == sec_email, "sec email wrong in event sheet"
        assert event_row["Ticket Type"] == form_data["event_tickets"]

def test_secondary_exists_as_nonexpired_primary(client):
    """
        Test when a user submits a secondary email that already exists as someone elses
        primary but it is not expired
        Clear members sheet, insert row with non expired secondary email, get event name,
        clear event sheet, build form, get csrf token, send POST request, make sure
        error1 renders

    """

    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Insert row for test
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    email = "email@email.com"
    new_prim_email = "email2@email.com"
    sec_email = "test2@email.com"
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = sec_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    records = get_wks_records(wks)
    row = records[0]
    assert row["Primary Email"] == email, "set up for test failed"
    token = generate_token(new_prim_email)


    # Get event name
    with client.application.app_context():
            event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    csrf_token = ""

    # get CSRF token for form
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

        form_data = {
                        "first_name": "AVASH_TEST",
                        "last_name": "ADHIKARI_TEST",
                        "primary_email": new_prim_email,
                        "confirm_primary": new_prim_email,
                        "secondary_email": email,
                        "confirm_secondary": email,
                        "register_event": "y",
                        "country_code": "",  
                        "csrf_token": csrf_token
                    }

        # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"


        # Send POST form data
    with client as c:
        token = generate_token(new_prim_email)
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)
        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 01")
        assert heading is not None, "did not render error1 template"

def test_secondary_exists_as_nonexpired_secondary(client):
    """
        Test for a secondary email existing as a non expired secondary email

        Clear members sheet, insert row with a nonexpired secondary email, get event name,
        clear event sheet, get csrf token, build form data, send POST request, make sure
        we render error1 template
    """

    # Clear members
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Insert row
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    email = "email@email.com"
    sec_email = "test2@email.com"
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = "vro@vro.com"
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = sec_email
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    wks.append_row(user)

    records = get_wks_records(wks)
    row = records[0]
    assert row["Secondary Email"] == sec_email, "set up for test failed"


    token = generate_token(email)

    # Get event name/ clear event sheet
    with client.application.app_context():
            event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    csrf_token = ""

    # get CSRF token for form
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    form_data = {
                    "first_name": "AVASH_TEST",
                    "last_name": "ADHIKARI_TEST",
                    "primary_email": email,
                    "confirm_primary": email,
                    "secondary_email": sec_email,
                    "confirm_secondary": sec_email,
                    "register_event": "y",
                    "country_code": "",  
                    "csrf_token": csrf_token
                }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"


    # Send POST form data
    with client as c:
        token = generate_token(email)
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)
        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h1", string="ERROR 01")
        assert heading is not None, "did not render error1 template"


def test_two_email_1_phone_happy_path(client):
    """
        Test for a full registration with two emails and 1 phone number.
        This is with the event
        Should render the otp form and in the google sheet we should

        Clear members sheet, get event name/clear event sheet, get csrf token,
        build form data, send POST request, make sure otp form gets rendered,
        and make sure we have the correct info in both members and event sheet
    """

    email = "test@test.com"
    token = generate_token(email)

    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name/clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    phone_number = "8057105809"
    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "bro@bro.com",
                "confirm_secondary": "bro@bro.com",
                "register_event": "y",
                "csrf_token": csrf_token,
                "country_code": "",  
                "country_code": "+1",
                "phone_number": phone_number,
                "confirm_phone_number": phone_number
    }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"


    # Send POST request
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Ensure OTP form gets rendered
        search_string = "Verify Your Phone Number"

        heading = soup.find("h4", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        # Ensure members sheet has correct info
        time.sleep(3)
        # asserting members fields
        records = get_wks_records(wks)
        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == "bro@bro.com", "sec email wrong in members sheet"
        complete_number = "1" + phone_number
        assert row["Phone Number"] == int(complete_number)

        # asserting event fields
        event_records = get_wks_records(event_wks)
        event_row = event_records[0]
        assert event_row["First Name"] == "AVASH_TEST", "first name wrong in event sheet"
        assert event_row["Last Name"] == "ADHIKARI_TEST", "last name wrong in event sheet"
        assert event_row["Membership Primary"] == email, "prim email wrong in event sheet"
        assert event_row["Membership Secondary"] == "bro@bro.com", "secondary email wrong in event sheet"
        assert event_row["Phone Number"] == complete_number, "phone number wrong in event sheet"
        assert event_row["Ticket Type"] == form_data["event_tickets"]


def test_1_email_1_phone_happy(client):
    """
        This tests for when a new user attempts to sign up with a new email and new phone number.
        It should work, render the otp form, and have the correct info in both the members
        and event sheets.
    """

    # Clear event sheet
    email = "test@test.com"
    token = generate_token(email)
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF Token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Build Form
    phone_number = "2092591247"
    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "",
                "confirm_secondary": "",
                "register_event": "y",
                "csrf_token": csrf_token,
                "country_code": "+1",
                "phone_number": phone_number,
                "confirm_phone_number": phone_number
    }
    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"

    # Send POST request
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Ensure OTP form gets rendered
        search_string = "Verify Your Phone Number"

        heading = soup.find("h4", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        # Ensure members sheet has correct info
        time.sleep(3)
        # asserting members fields
        records = get_wks_records(wks)
        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == "", "sec email wrong in members sheet"
        complete_number = "1" + phone_number
        assert row["Phone Number"] == int(complete_number)

        # asserting event fields
        event_records = get_wks_records(event_wks)
        event_row = event_records[0]
        assert event_row["First Name"] == "AVASH_TEST", "first name wrong in event sheet"
        assert event_row["Last Name"] == "ADHIKARI_TEST", "last name wrong in event sheet"
        assert event_row["Membership Primary"] == email, "prim email wrong in event sheet"
        assert event_row["Membership Secondary"] == "", "secondary email wrong in event sheet"
        complete_number = "1" + phone_number
        assert event_row["Phone Number"] == int(complete_number), "phone number wrong in event sheet"
        assert event_row["Ticket Type"] == form_data["event_tickets"]


def test_two_email_one_phone_no_event(client):
    """
        This tests for a new registration with two emails and one phone with no event
        It should return the OTP page and only update the members sheet.
    """

    # Clear event sheet
    email = "test@test.com"
    token = generate_token(email)
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)


    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF Token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]


    # Build Form
    phone_number = "2092591247"
    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "bro@bro.com",
                "confirm_secondary": "bro@bro.com",
                "csrf_token": csrf_token,
                "country_code": "+1",
                "phone_number": phone_number,
                "confirm_phone_number": phone_number
    }
    # add info fields to form data
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

    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Ensure OTP form gets rendered
        search_string = "Verify Your Phone Number"

        heading = soup.find("h4", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        # Ensure members sheet has correct info
        time.sleep(3)
        # asserting members fields
        records = get_wks_records(wks)
        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == "bro@bro.com", "sec email wrong in members sheet"
        complete_number = "1" + phone_number
        assert row["Phone Number"] == int(complete_number)

        # asserting event fields
        event_records = get_wks_records(event_wks)
        print(event_records)
        assert len(event_records) == 0, "event sheet was updated"


def test_one_email_one_phone_no_event(client):
    """
        This tests for a new registration with one email and one phone with no event
        It should return the OTP page and only update the members sheet.
    """

    # Clear members sheet
    email = "test@test.com"
    token = generate_token(email)
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)


    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)


    # Get CSRF Token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]


    # Build Form
    phone_number = "2092591247"
    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "",
                "confirm_secondary": "",
                "csrf_token": csrf_token,
                "country_code": "+1",
                "phone_number": phone_number,
                "confirm_phone_number": phone_number
    }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"


    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Ensure OTP form gets rendered
        search_string = "Verify Your Phone Number"

        heading = soup.find("h4", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."

        # Ensure members sheet has correct info
        time.sleep(3)
        # asserting members fields
        records = get_wks_records(wks)
        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == email, "prim email wrong in members sheet"
        assert row["Secondary Email"] == "", "sec email wrong in members sheet"
        complete_number = "1" + phone_number
        assert row["Phone Number"] == int(complete_number)

        # asserting event fields
        event_records = get_wks_records(event_wks)
        assert len(event_records) == 0, "event sheet was updated"


def test_one_email_and_phone_with_num_in_use(client):
    """
        This tests for when a new registration with two emails and a phone number attempts to register with
        a phone number that is already in use.

        This should render error3.html and make no changes to event or members sheet
    """

    # Clear members sheet
    email = "test@test.com"
    token = generate_token(email)
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]


    # Insert a row into members sheet with the phone number the new user will use
    phone_number = "2092591247"
    full_number = "+1" + phone_number
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = "vro@vro.com"
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = "bro@bro.com"
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = full_number
    wks.append_row(user)
    time.sleep(2)

    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "",
                "confirm_secondary": "",
                "csrf_token": csrf_token,
                "country_code": "+1",
                "phone_number": phone_number,
                "confirm_phone_number": phone_number
    }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"

    # Send POST request
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)

        # Ensure error3 template gets rendered
        search_string = "ERROR 03"

        heading = soup.find("h1", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."


    records = get_wks_records(wks)
    num_records = len(records)
    assert num_records == 1, "members sheet has stuff"
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    assert num_event_records == 0, "event sheet has stuff"


def test_two_emails_and_phone_with_num_in_use(client):
    """
        This tests for when a new registration with one email and a phone number attempts to register with
        a phone number that is already in use.

        This should render error3.html and make no changes to event or members sheet
    """

    # Clear members sheet
    email = "test@test.com"
    token = generate_token(email)
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]


    # Insert a row into members sheet with the phone number the new user will use
    phone_number = "2092591247"
    full_number = "+1" + phone_number
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = "vro@vro.com"
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = "bro@bro.com"
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = full_number
    wks.append_row(user)
    time.sleep(2)


    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "jo@jo.com",
                "confirm_secondary": "jo@jo.com",
                "csrf_token": csrf_token,
                "country_code": "+1",
                "phone_number": phone_number,
                "confirm_phone_number": phone_number
    }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"

    # Send POST request
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Ensure error3 template gets rendered
        search_string = "ERROR 03"

        heading = soup.find("h1", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."


    records = get_wks_records(wks)
    num_records = len(records)
    assert num_records == 1, "members sheet has stuff"
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    assert num_event_records == 0, "event sheet has stuff"



def test_one_email_one_phone_email_already_in_use(client):
    """
        Test a new registration with an email and a phone number. The email is already in use
        but the phone number is open. This should fail and return error1.html
    """

    # Clear members sheet
    email = "test@test.com"
    token = generate_token(email)
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)


    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)


    # Get CSRF token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]


    # Insert a row into members sheet with the phone number the new user will use
    phone_number = "2092591247"
    full_number = "+1" + phone_number
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = "bro@bro.com"
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = full_number
    wks.append_row(user)
    time.sleep(2)

    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "",
                "confirm_secondary": "",
                "csrf_token": csrf_token,
                "country_code": "+1",
                "phone_number": "8057105809",
                "confirm_phone_number": "8057105809"
    }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"

    # Send POST request
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)

        # Ensure error3 template gets rendered
        search_string = "ERROR 01"

        heading = soup.find("h1", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."


    records = get_wks_records(wks)
    num_records = len(records)
    assert num_records == 1, "members sheet has stuff"
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    assert num_event_records == 0, "event sheet has stuff"


def test_two_email_one_email_prim_in_use(client):
    """
        This tests for a new registration with two emails and one phone but the primary
        email is already in use
    """

    # Clear members sheet
    email = "test@test.com"
    token = generate_token(email)
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)


    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Insert a row into members sheet with the primary email that the new user wil use
    phone_number = "2092591247"
    full_number = "+1" + phone_number
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = "bro@bro.com"
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = full_number
    wks.append_row(user)
    time.sleep(2)

    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "jo@jo.com",
                "confirm_secondary": "jo@jo.com",
                "csrf_token": csrf_token,
                "country_code": "+1",
                "phone_number": "8057105809",
                "confirm_phone_number": "8057105809"
    }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"

    # Send POST request
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)

        # Ensure error3 template gets rendered
        search_string = "ERROR 01"

        heading = soup.find("h1", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."


    records = get_wks_records(wks)
    num_records = len(records)
    assert num_records == 1, "members sheet has stuff"
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    assert num_event_records == 0, "event sheet has stuff"


def test_two_email_one_email_sec_in_use(client):
    """
        This tests for a new registration with two emails and one phone but the secondary
        email is already in use
    """

    # Clear members sheet
    email = "test@test.com"
    token = generate_token(email)
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)


    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        # assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
        event_wks = sh.worksheet(event_name)
        event_records = get_wks_records(event_wks)
        num_event_records = len(event_records)
        if num_event_records > 1:
            event_wks.delete_rows(2, num_event_records)
        elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF token
    csrf_token = ""
    with client as c:
        response = c.get(f"/membership/full-registration/{token}")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Insert a row into members sheet with the primary email that the new user wil use
    phone_number = "2092591247"
    full_number = "+1" + phone_number
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
    user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = email
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = "bro@bro.com"
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = full_number
    wks.append_row(user)
    time.sleep(2)

    # Build form data
    form_data = {
                "first_name": "AVASH_TEST",
                "last_name": "ADHIKARI_TEST",
                "primary_email": email,
                "confirm_primary": email,
                "secondary_email": "bro@bro.com",
                "confirm_secondary": "bro@bro.com",
                "csrf_token": csrf_token,
                "country_code": "+1",
                "phone_number": "8057105809",
                "confirm_phone_number": "8057105809"
    }

    # add info fields to form data
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

    event_name = ""
    # add event fields to form data
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        ticket_types = event_obj.tickets.split("\n")
        form_data["event_tickets"] = ticket_types[0]

        for question in event_obj.questions.split("\n"):
            form_data["event_" + question] = "test answer from test_registration_happy"

    # Send POST request
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup)

        # Ensure error3 template gets rendered
        search_string = "ERROR 01"

        heading = soup.find("h1", string=search_string)
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The error page was not rendered. The registration may have failed."


    records = get_wks_records(wks)
    num_records = len(records)
    assert num_records == 1, "members sheet has stuff"
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    assert num_event_records == 0, "event sheet has stuff"


def test_signup_two_emails_no_phone_happy_path(client):
    """
    Test for a new /signup POST request with two emails and no phone number.
    This should render instructions_sent.html and create a user record in the members sheet.
    """
    
    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        if event_obj is not None:
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF token for form
    csrf_token = ""
    with client as c:
        response = c.get("/membership/signup")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Build form data with two emails and no phone
    form_data = {
        "first_name": "AVASH_TEST",
        "last_name": "ADHIKARI_TEST", 
        "primary_email": "test@test.com",
        "confirm_primary": "test@test.com",
        "secondary_email": "bro@bro.com",
        "confirm_secondary": "bro@bro.com",
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "country_code": "",  # No phone
        "phone_number": "",
        "confirm_phone_number": "",
        "phone_subscribe": "",
        "csrf_token": csrf_token
    }

    # Add info fields to form data
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

    # Send POST form data
    with client as c:
        response = c.post("/membership/signup", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Check if the instructions_sent page was rendered by looking for its content
        instructions_text = soup.find("p", string="Please check them to complete the registration (eventually check spam folders).")
        assert instructions_text is not None, "The instructions_sent page was not rendered. The registration may have failed."

        # Ensure the form was not re-rendered
        first_name_input = soup.find("input", {"name": "first_name"})
        assert not first_name_input, "The form has been re-rendered instead of showing instructions"

        # Wait for background thread to complete
        time.sleep(3)
        
        # Assert members sheet has correct info
        records = get_wks_records(wks)
        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == "test@test.com", "primary email wrong in members sheet"
        assert row["Secondary Email"] == "bro@bro.com", "secondary email wrong in members sheet"
        assert row["Primary Verified"] == "FALSE", "primary verified should be FALSE"
        assert row["Secondary Verified"] == "FALSE", "secondary verified should be FALSE"
        assert row["Info Completed"] == "FALSE", "info completed should be FALSE"
        
        # Phone number should be empty since none was provided
        phone_number = row.get("Phone Number", "")
        assert phone_number == "", "phone number should be empty when no phone provided"


def test_signup_one_email_one_phone_otp_happy_path(client):
    """
    Test for a new /signup POST request with one email and one phone number.
    This should render the OTP form and create a user record in the members sheet.
    """
    
    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        if event_obj is not None:
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF token for form
    csrf_token = ""
    with client as c:
        response = c.get("/membership/signup")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Build form data with one email and one phone
    phone_number = "8057105809"
    form_data = {
        "first_name": "AVASH_TEST",
        "last_name": "ADHIKARI_TEST", 
        "primary_email": "test@test.com",
        "confirm_primary": "test@test.com",
        "secondary_email": "",  # No secondary email
        "confirm_secondary": "",
        "primary_subscribe": "y",
        "secondary_subscribe": "",
        "country_code": "+1",  # Phone provided
        "phone_number": phone_number,
        "confirm_phone_number": phone_number,
        "phone_subscribe": "y",
        "csrf_token": csrf_token
    }

    # Add info fields to form data
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

    # Send POST form data
    with client as c:
        response = c.post("/membership/signup", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Check if the OTP form was rendered by looking for its heading
        search_string = "Verify Your Phone Number"
        heading = soup.find("h4", string=search_string)
        assert heading is not None, "The OTP verification page was not rendered. The phone verification may have failed."

        # Ensure the form was not re-rendered
        first_name_input = soup.find("input", {"name": "first_name"})
        assert not first_name_input, "The form has been re-rendered instead of showing OTP form"

        # Wait for background thread to complete
        time.sleep(3)
        
        # Assert members sheet has correct info
        records = get_wks_records(wks)
        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == "test@test.com", "primary email wrong in members sheet"
        assert row["Secondary Email"] == "", "secondary email should be empty"
        assert row["Primary Verified"] == "FALSE", "primary verified should be FALSE"
        assert row["Secondary Verified"] == "FALSE", "secondary verified should be FALSE"
        assert row["Info Completed"] == "FALSE", "info completed should be FALSE"
        
        # Phone number should be stored with proper formatting
        # Note: Google Sheets may convert phone numbers to integers, losing the + prefix
        stored_phone = str(row.get("Phone Number", ""))
        expected_phone = "1" + phone_number  # Google Sheets stores as integer without +
        assert stored_phone == expected_phone, f"phone number wrong in members sheet: expected {expected_phone}, got {stored_phone}"


def test_signup_phone_number_already_exists_error(client):
    """
    Test for a new /signup POST request with a phone number that already exists.
    This should render error3.html and not create a user record.
    """
    
    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        if event_obj is not None:
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Insert a user with the phone number that the new user will try to use
    phone_number = "8057105809"
    full_number = "+1" + phone_number
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "EXISTING_USER"
    user[wks_columns["Last Name"] - 1] = "EXISTING_USER"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = "existing@test.com"
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = ""
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = full_number
    wks.append_row(user)
    time.sleep(2)

    # Get CSRF token for form
    csrf_token = ""
    with client as c:
        response = c.get("/membership/signup")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Build form data with the same phone number that already exists
    form_data = {
        "first_name": "NEW_USER",
        "last_name": "NEW_USER", 
        "primary_email": "new@test.com",
        "confirm_primary": "new@test.com",
        "secondary_email": "",  # No secondary email
        "confirm_secondary": "",
        "primary_subscribe": "y",
        "secondary_subscribe": "",
        "country_code": "+1",  # Same phone number
        "phone_number": phone_number,
        "confirm_phone_number": phone_number,
        "phone_subscribe": "y",
        "csrf_token": csrf_token
    }

    # Add info fields to form data
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

    # Send POST form data
    with client as c:
        response = c.post("/membership/signup", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Check if the error3 page was rendered by looking for its heading
        error_heading = soup.find("h1", string="ERROR 03")
        assert error_heading is not None, "The error3 page was not rendered. The phone conflict should have been detected."

        # Ensure the form was not re-rendered
        first_name_input = soup.find("input", {"name": "first_name"})
        assert not first_name_input, "The form has been re-rendered instead of showing error"

        # Wait a moment to ensure no background processing
        time.sleep(2)
        
        # Assert that no new user was created (should still only have the existing user)
        records = get_wks_records(wks)
        assert len(records) == 1, "A new user was created when it should have been blocked"
        
        # Verify the existing user is still there
        row = records[0]
        assert row["First Name"] == "EXISTING_USER", "Existing user was modified"
        assert row["Primary Email"] == "existing@test.com", "Existing user email was modified"
        
        # Verify the phone number is still associated with the existing user
        stored_phone = str(row.get("Phone Number", ""))
        expected_phone = "1" + phone_number  # Google Sheets stores as integer without +
        assert stored_phone == expected_phone, f"Existing user's phone number was modified: expected {expected_phone}, got {stored_phone}"


def test_signup_two_emails_one_phone_otp_happy_path(client):
    """
    Test for a new /signup POST request with two emails and one phone number.
    This should render the OTP form and create a user record in the members sheet.
    """
    
    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        if event_obj is not None:
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Get CSRF token for form
    csrf_token = ""
    with client as c:
        response = c.get("/membership/signup")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Build form data with two emails and one phone
    phone_number = "8057105809"
    form_data = {
        "first_name": "AVASH_TEST",
        "last_name": "ADHIKARI_TEST", 
        "primary_email": "test@test.com",
        "confirm_primary": "test@test.com",
        "secondary_email": "bro@bro.com",
        "confirm_secondary": "bro@bro.com",
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "country_code": "+1",  # Phone provided
        "phone_number": phone_number,
        "confirm_phone_number": phone_number,
        "phone_subscribe": "y",
        "csrf_token": csrf_token
    }

    # Add info fields to form data
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

    # Send POST form data
    with client as c:
        response = c.post("/membership/signup", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Check if the OTP form was rendered by looking for its heading
        search_string = "Verify Your Phone Number"
        heading = soup.find("h4", string=search_string)
        assert heading is not None, "The OTP verification page was not rendered. The phone verification may have failed."

        # Ensure the form was not re-rendered
        first_name_input = soup.find("input", {"name": "first_name"})
        assert not first_name_input, "The form has been re-rendered instead of showing OTP form"

        # Wait for background thread to complete
        time.sleep(3)
        
        # Assert members sheet has correct info
        records = get_wks_records(wks)
        row = records[0]
        assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
        assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
        assert row["Primary Email"] == "test@test.com", "primary email wrong in members sheet"
        assert row["Secondary Email"] == "bro@bro.com", "secondary email wrong in members sheet"
        assert row["Primary Verified"] == "FALSE", "primary verified should be FALSE"
        assert row["Secondary Verified"] == "FALSE", "secondary verified should be FALSE"
        assert row["Info Completed"] == "FALSE", "info completed should be FALSE"
        
        # Phone number should be stored with proper formatting
        # Note: Google Sheets may convert phone numbers to integers, losing the + prefix
        stored_phone = str(row.get("Phone Number", ""))
        expected_phone = "1" + phone_number  # Google Sheets stores as integer without +
        assert stored_phone == expected_phone, f"phone number wrong in members sheet: expected {expected_phone}, got {stored_phone}"


def test_signup_two_emails_one_phone_conflict_error(client):
    """
    Test for a new /signup POST request with two emails and a phone number that already exists.
    This should render error3.html and not create a user record.
    """
    
    # Clear members sheet
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)

    # Get event name and clear event sheet
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        if event_obj is not None:
            event_name = event_obj.name
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            num_event_records = len(event_records)
            if num_event_records > 1:
                event_wks.delete_rows(2, num_event_records)
            elif num_event_records > 0:
                event_wks.delete_rows(2)

    # Insert a user with the phone number that the new user will try to use
    phone_number = "8057105809"
    full_number = "+1" + phone_number
    wks_columns = get_wks_columns(wks)
    user = ["" for i in range(len(wks_columns))]
    user[wks_columns["Order"] - 1] = "1"
    user[wks_columns["First Name"] - 1] = "EXISTING_USER"
    user[wks_columns["Last Name"] - 1] = "EXISTING_USER"
    user[wks_columns["When Started"] - 1] = "TEST START"
    user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
    user[wks_columns["Primary Email"] - 1] = "existing@test.com"
    user[wks_columns["Primary Verified"] - 1] = "TRUE"
    user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
    user[wks_columns["Primary Expired"] - 1] = "FALSE"
    user[wks_columns["Primary Bounced"] - 1] = ""
    user[wks_columns["Secondary Email"] - 1] = "existing2@test.com"
    user[wks_columns["Secondary Verified"] - 1] = "FALSE"
    user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
    user[wks_columns["Secondary Expired"] - 1] = "FALSE"
    user[wks_columns["Secondary Bounced"] - 1] = ""
    user[wks_columns["Info Completed"] - 1] = "TRUE"
    user[wks_columns["Phone Number"] - 1] = full_number
    wks.append_row(user)
    time.sleep(2)

    # Get CSRF token for form
    csrf_token = ""
    with client as c:
        response = c.get("/membership/signup")
        soup = BeautifulSoup(response.data, "html.parser")
        csrf_token_input = soup.find("input", {"name": "csrf_token"})
        assert csrf_token_input, "CSRF token not found in the form."
        csrf_token = csrf_token_input["value"]

    # Build form data with two emails and the same phone number that already exists
    form_data = {
        "first_name": "NEW_USER",
        "last_name": "NEW_USER", 
        "primary_email": "new@test.com",
        "confirm_primary": "new@test.com",
        "secondary_email": "new2@test.com",
        "confirm_secondary": "new2@test.com",
        "primary_subscribe": "y",
        "secondary_subscribe": "y",
        "country_code": "+1",  # Same phone number
        "phone_number": phone_number,
        "confirm_phone_number": phone_number,
        "phone_subscribe": "y",
        "csrf_token": csrf_token
    }

    # Add info fields to form data
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

    # Send POST form data
    with client as c:
        response = c.post("/membership/signup", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")

        # Check if the error3 page was rendered by looking for its heading
        error_heading = soup.find("h1", string="ERROR 03")
        assert error_heading is not None, "The error3 page was not rendered. The phone conflict should have been detected."

        # Ensure the form was not re-rendered
        first_name_input = soup.find("input", {"name": "first_name"})
        assert not first_name_input, "The form has been re-rendered instead of showing error"

        # Wait a moment to ensure no background processing
        time.sleep(2)
        
        # Assert that no new user was created (should still only have the existing user)
        records = get_wks_records(wks)
        assert len(records) == 1, "A new user was created when it should have been blocked"
        
        # Verify the existing user is still there
        row = records[0]
        assert row["First Name"] == "EXISTING_USER", "Existing user was modified"
        assert row["Primary Email"] == "existing@test.com", "Existing user email was modified"
        assert row["Secondary Email"] == "existing2@test.com", "Existing user secondary email was modified"
        
        # Verify the phone number is still associated with the existing user
        stored_phone = str(row.get("Phone Number", ""))
        expected_phone = "1" + phone_number  # Google Sheets stores as integer without +
        assert stored_phone == expected_phone, f"Existing user's phone number was modified: expected {expected_phone}, got {stored_phone}"
