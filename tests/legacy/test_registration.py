import time
from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event
from project import get_wks_columns, wks, get_wks_records, sh

# def test_happy_path_with_event(client):
#     """
#         Tests the happy path for the /full-registration/<token> route including event registration
#     """
#     email = "avashraj328@gmail.com"
#     token = generate_token(email)

#     # make sure we are on the testing sheet
#     worksheet_title = wks.title
#     assert worksheet_title == "MEMBERS_FOR_TESTING", "YOU ARE ON PROD WHAT THE FUCK"

#     records = get_wks_records(wks)
#     if len(records) > 0:
#         wks.delete_rows(2)

#     with client.application.app_context():
#         event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
#         event_name = event_obj.name
#         assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
#         event_wks = sh.worksheet(event_name)
#         event_records = get_wks_records(event_wks)
#         if len(event_records) > 0:
#             event_wks.delete_rows(2)
#             time.sleep(5)

#     csrf_token = ""

#     # get CSRF token for form
#     with client as c:
#         response = c.get(f"/membership/full-registration/{token}")
#         soup = BeautifulSoup(response.data, "html.parser")
#         csrf_token_input = soup.find("input", {"name": "csrf_token"})
#         assert csrf_token_input, "CSRF token not found in the form."
#         csrf_token = csrf_token_input["value"]

#     form_data = {
#                 "first_name": "AVASH_TEST",
#                 "last_name": "ADHIKARI_TEST",
#                 "primary_email": email,
#                 "confirm_primary": email,
#                 "secondary_email": "bro@bro.com",
#                 "confirm_secondary": "bro@bro.com",
#                 "register_event": "y",
#                 "csrf_token": csrf_token
#             }

#     # add info fields to form data
#     with client.application.app_context():
#         required_fields = edit_form.query.filter_by(required=True).all()
#         for field in required_fields:
#             # Provide dummy data for dynamically generated required fields.
#             if field.field_type == "Checkbox":
#                 # For checkboxes, WTForms expects a list of values.
#                 # We'll just select the first option by its index '0'.
#                 form_data[field.label] = '0'
#             elif field.field_type == "Radio":
#                 # For radio buttons, we provide the value of the choice.
#                 options = field.options.split('\n')
#                 if options:
#                     form_data[field.label] = options[0]
#             else: # For StringField, TextAreaField, etc.
#                 form_data[field.label] = f"Test data for {field.label}"

#     event_name = ""
#     # add event fields to form data
#     with client.application.app_context():
#         event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
#         event_name = event_obj.name
#         ticket_types = event_obj.tickets.split("\n")
#         form_data["event_tickets"] = ticket_types[0]

#         for question in event_obj.questions.split("\n"):
#             form_data["event_" + question] = "test answer from test_registration_happy"


#     # Send POST form data
#     with client as c:
#         response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

#         soup = BeautifulSoup(response.data, "html.parser")

#         # Check if the receipt page was rendered by looking for its heading.
#         heading = soup.find("h1", string="I2G Membership Completed")
#         input = soup.find("input", {"name": "first_name"})
#         assert not input, "The form has been rerendered"
#         assert heading is not None, "The receipt page was not rendered. The registration may have failed."

#         time.sleep(5)
#         # asserting members fields
#         records = get_wks_records(wks)
#         row = records[0]
#         assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
#         assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
#         assert row["Primary Email"] == email, "prim email wrong in members sheet"
#         assert row["Secondary Email"] == "bro@bro.com", "sec email wrong in members sheet"

#         # asserting event fields
#         event_records = get_wks_records(event_wks)
#         event_row = event_records[0]
#         assert event_row["First Name"] == "AVASH_TEST", "first name wrong in event sheet"
#         assert event_row["Last Name"] == "ADHIKARI_TEST", "last name wrong in event sheet"
#         assert event_row["Membership Primary"] == email, "prim email wrong in event sheet"
#         assert event_row["Membership Secondary"] == "bro@bro.com", "sec email wrong in event sheet"
#         assert event_row["Ticket Type"] == form_data["event_tickets"]

# def test_happy_path_without_event(client):
#     """
#         Tests the happy path for the /full-registration/<token> route without event registration
#     """
#     email = "avashraj328@gmail.com"
#     token = generate_token(email)

#     # make sure we are on the testing sheet
#     worksheet_title = wks.title
#     assert worksheet_title == "MEMBERS_FOR_TESTING", "YOU ARE ON PROD WHAT THE FUCK"

#     records = get_wks_records(wks)
#     if len(records) > 0:
#         wks.delete_rows(2)
#     with client.application.app_context():
#         event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
#         event_name = event_obj.name
#         event_wks = sh.worksheet(event_name)
#         event_records = get_wks_records(event_wks)
#         if len(event_records) > 0:
#             event_wks.delete_rows(2)
#             time.sleep(5)

#     csrf_token = ""

#     # get CSRF token for form
#     with client as c:
#         response = c.get(f"/membership/full-registration/{token}")
#         soup = BeautifulSoup(response.data, "html.parser")
#         csrf_token_input = soup.find("input", {"name": "csrf_token"})
#         assert csrf_token_input, "CSRF token not found in the form."
#         csrf_token = csrf_token_input["value"]

#     form_data = {
#                 "first_name": "AVASH_TEST",
#                 "last_name": "ADHIKARI_TEST",
#                 "primary_email": email,
#                 "confirm_primary": email,
#                 "secondary_email": "bro@bro.com",
#                 "confirm_secondary": "bro@bro.com",
#                 "csrf_token": csrf_token
#             }

#     # add info fields to form data
#     with client.application.app_context():
#         required_fields = edit_form.query.filter_by(required=True).all()
#         for field in required_fields:
#             # Provide dummy data for dynamically generated required fields.
#             if field.field_type == "Checkbox":
#                 # For checkboxes, WTForms expects a list of values.
#                 # We'll just select the first option by its index '0'.
#                 form_data[field.label] = '0'
#             elif field.field_type == "Radio":
#                 # For radio buttons, we provide the value of the choice.
#                 options = field.options.split('\n')
#                 if options:
#                     form_data[field.label] = options[0]
#             else: # For StringField, TextAreaField, etc.
#                 form_data[field.label] = f"Test data for {field.label}"

#     with client as c:
#         response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

#         soup = BeautifulSoup(response.data, "html.parser")

#         # Check if the receipt page was rendered by looking for its heading.
#         heading = soup.find("h1", string="I2G Membership Completed")
#         input = soup.find("input", {"name": "first_name"})
#         assert not input, "The form has been rerendered"
#         assert heading is not None, "The receipt page was not rendered. The registration may have failed."

#         time.sleep(5)
#         # asserting members fields
#         records = get_wks_records(wks)
#         event_records = get_wks_records(event_wks)

#         row = records[0]
#         assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
#         assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
#         assert row["Primary Email"] == email, "prim email wrong in members sheet"
#         assert row["Secondary Email"] == "bro@bro.com", "sec email wrong in members sheet"

#         assert len(event_records) == 0, "event records has stuff in it"

# def test_primary_email_already_exists(client):
#     """
#         Tests /full-registration/<token> route including event registration when we
#         use a primary email that already exists
#         should return error 1 template
#     """

#     # delete old test stuff
#     records = get_wks_records(wks)
#     if len(records) > 0:
#         wks.delete_rows(2)

#     # add email for this test
#     wks_columns = get_wks_columns(wks)
#     user = ["" for i in range(len(wks_columns))]
#     email = "test@email.com"
#     sec_email = "test2@email.com"
#     user[wks_columns["Order"] - 1] = "1"
#     user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
#     user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
#     user[wks_columns["When Started"] - 1] = "TEST START"
#     user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
#     user[wks_columns["Primary Email"] - 1] = email
#     user[wks_columns["Primary Verified"] - 1] = "TRUE"
#     user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
#     user[wks_columns["Primary Expired"] - 1] = "FALSE"
#     user[wks_columns["Primary Bounced"] - 1] = ""
#     user[wks_columns["Secondary Email"] - 1] = "second@email.com"
#     user[wks_columns["Secondary Verified"] - 1] = "FALSE"
#     user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
#     user[wks_columns["Secondary Expired"] - 1] = "FALSE"
#     user[wks_columns["Secondary Bounced"] - 1] = ""
#     user[wks_columns["Info Completed"] - 1] = "TRUE"
#     wks.append_row(user)

#     records = get_wks_records(wks)
#     row = records[0]
#     assert row["Primary Email"] == email

#     token = generate_token(email)

#     with client as c:
#             response = c.get(f"/membership/full-registration/{token}")
#             soup = BeautifulSoup(response.data, "html.parser")
#             heading = soup.find("h1", string="ERROR 01")
#             assert heading is not None, "did not render error1 template"


# def test_secondary_already_exists(client):
#     """
#         Tests /full-registration/<token> route including event registration when we
#         use a secondary email that already exists
#         should return error 1 template
#     """

#     records = get_wks_records(wks)
#     if len(records) > 0:
#         wks.delete_rows(2)

#     # add email for this test
#     wks_columns = get_wks_columns(wks)
#     user = ["" for i in range(len(wks_columns))]
#     sec_email = "test2@email.com"
#     user[wks_columns["Order"] - 1] = "1"
#     user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
#     user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
#     user[wks_columns["When Started"] - 1] = "TEST START"
#     user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
#     user[wks_columns["Primary Email"] - 1] = "email@email.com"
#     user[wks_columns["Primary Verified"] - 1] = "TRUE"
#     user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
#     user[wks_columns["Primary Expired"] - 1] = "FALSE"
#     user[wks_columns["Primary Bounced"] - 1] = ""
#     user[wks_columns["Secondary Email"] - 1] = sec_email
#     user[wks_columns["Secondary Verified"] - 1] = "FALSE"
#     user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
#     user[wks_columns["Secondary Expired"] - 1] = "FALSE"
#     user[wks_columns["Secondary Bounced"] - 1] = ""
#     user[wks_columns["Info Completed"] - 1] = "TRUE"
#     wks.append_row(user)

#     records = get_wks_records(wks)
#     row = records[0]
#     assert row["Secondary Email"] == sec_email

#     token = generate_token(sec_email)

#     with client as c:
#             response = c.get(f"/membership/full-registration/{token}")
#             soup = BeautifulSoup(response.data, "html.parser")
#             heading = soup.find("h1", string="ERROR 01")
#             assert heading is not None, "did not render error1 template"

# def test_secondary_exists_as_expired_primary(client):
#     """
#         Test when a user submits a secondary email that already exists as someone elses
#         primary but it is expired

#         Should work
#     """

#     records = get_wks_records(wks)
#     if len(records) > 0:
#         wks.delete_rows(2)

#     wks_columns = get_wks_columns(wks)
#     user = ["" for i in range(len(wks_columns))]
#     email = "email@email.com"
#     new_prim_email = "email2@email.com"
#     sec_email = "test2@email.com"
#     user[wks_columns["Order"] - 1] = "1"
#     user[wks_columns["First Name"] - 1] = "TEST FIRST NAME"
#     user[wks_columns["Last Name"] - 1] = "TEST LAST NAME"
#     user[wks_columns["When Started"] - 1] = "TEST START"
#     user[wks_columns["Last Updated"] - 1] = "TEST UPDATE"
#     user[wks_columns["Primary Email"] - 1] = email
#     user[wks_columns["Primary Verified"] - 1] = "TRUE"
#     user[wks_columns["Primary Subscribed"] - 1] = "TRUE"
#     user[wks_columns["Primary Expired"] - 1] = "TRUE"
#     user[wks_columns["Primary Bounced"] - 1] = ""
#     user[wks_columns["Secondary Email"] - 1] = sec_email
#     user[wks_columns["Secondary Verified"] - 1] = "FALSE"
#     user[wks_columns["Secondary Subscribed"] - 1] = "FALSE"
#     user[wks_columns["Secondary Expired"] - 1] = "FALSE"
#     user[wks_columns["Secondary Bounced"] - 1] = ""
#     user[wks_columns["Info Completed"] - 1] = "TRUE"
#     wks.append_row(user)

#     records = get_wks_records(wks)
#     row = records[0]
#     assert row["Primary Email"] == email, "set up for test failed"


#     token = generate_token(new_prim_email)

#     # make sure we are on the testing sheet
#     worksheet_title = wks.title
#     assert worksheet_title == "MEMBERS_FOR_TESTING", "YOU ARE ON PROD WHAT THE FUCK"

#     with client.application.app_context():
#             event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
#             event_name = event_obj.name
#             assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
#             event_wks = sh.worksheet(event_name)
#             event_records = get_wks_records(event_wks)
#             if len(event_records) > 0:
#                 event_wks.delete_rows(2)
#                 time.sleep(5)

#     csrf_token = ""

#     # get CSRF token for form
#     with client as c:
#         response = c.get(f"/membership/full-registration/{token}")
#         soup = BeautifulSoup(response.data, "html.parser")
#         csrf_token_input = soup.find("input", {"name": "csrf_token"})
#         assert csrf_token_input, "CSRF token not found in the form."
#         csrf_token = csrf_token_input["value"]

#     form_data = {
#                     "first_name": "AVASH_TEST",
#                     "last_name": "ADHIKARI_TEST",
#                     "primary_email": new_prim_email,
#                     "confirm_primary": new_prim_email,
#                     "secondary_email": email,
#                     "confirm_secondary": email,
#                     "register_event": "y",
#                     "csrf_token": csrf_token
#                 }

#     # add info fields to form data
#     with client.application.app_context():
#         required_fields = edit_form.query.filter_by(required=True).all()
#         for field in required_fields:
#             # Provide dummy data for dynamically generated required fields.
#             if field.field_type == "Checkbox":
#                 # For checkboxes, WTForms expects a list of values.
#                 # We'll just select the first option by its index '0'.
#                 form_data[field.label] = '0'
#             elif field.field_type == "Radio":
#                 # For radio buttons, we provide the value of the choice.
#                 options = field.options.split('\n')
#                 if options:
#                     form_data[field.label] = options[0]
#             else: # For StringField, TextAreaField, etc.
#                 form_data[field.label] = f"Test data for {field.label}"

#     event_name = ""
#     # add event fields to form data
#     with client.application.app_context():
#         event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
#         event_name = event_obj.name
#         ticket_types = event_obj.tickets.split("\n")
#         form_data["event_tickets"] = ticket_types[0]

#         for question in event_obj.questions.split("\n"):
#             form_data["event_" + question] = "test answer from test_registration_happy"


#     # Send POST form data
#     with client as c:
#         token = generate_token(new_prim_email)
#         response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

#         soup = BeautifulSoup(response.data, "html.parser")

#         # Check if the receipt page was rendered by looking for its heading.
#         heading = soup.find("h1", string="I2G Membership Completed")
#         input = soup.find("input", {"name": "first_name"})
#         assert not input, "The form has been rerendered"
#         assert heading is not None, "The receipt page was not rendered. The registration may have failed."

#         time.sleep(5)
#         # asserting members fields
#         records = get_wks_records(wks)
#         row = records[1]
#         assert row["First Name"] == "AVASH_TEST", "first name wrong in members sheet"
#         assert row["Last Name"] == "ADHIKARI_TEST", "last name wrong in members sheet"
#         assert row["Primary Email"] == new_prim_email, "prim email wrong in members sheet"
#         assert row["Secondary Email"] == email, "sec email wrong in members sheet"

#         # asserting event fields
#         event_records = get_wks_records(event_wks)
#         event_row = event_records[0]
#         assert event_row["First Name"] == "AVASH_TEST", "first name wrong in event sheet"
#         assert event_row["Last Name"] == "ADHIKARI_TEST", "last name wrong in event sheet"
#         assert event_row["Membership Primary"] == new_prim_email, "prim email wrong in event sheet"
#         assert event_row["Membership Secondary"] == email, "sec email wrong in event sheet"
#         assert event_row["Ticket Type"] == form_data["event_tickets"]

def test_secondary_exists_as_expired_secondary(client):
    """
            Test when a user submits a secondary email that already exists as someone elses
            secondary but it is expired

            Should work
    """

    records = get_wks_records(wks)
    if len(records) > 0:
        wks.delete_rows(2)

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

    # make sure we are on the testing sheet
    worksheet_title = wks.title
    assert worksheet_title == "MEMBERS_FOR_TESTING", "YOU ARE ON PROD WHAT THE FUCK"

    with client.application.app_context():
            event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
            event_name = event_obj.name
            assert event_name == "TESTING EVENT FOR CODEBASE", "YOU ARE NOT ON THE TESTING SHEET"
            event_wks = sh.worksheet(event_name)
            event_records = get_wks_records(event_wks)
            if len(event_records) > 0:
                event_wks.delete_rows(2)
                time.sleep(5)

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

        time.sleep(5)
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
