import time
from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event
from project import wks, get_wks_records, sh

def test_email_form(client):
    email = "avashraj328@gmail.com"
    token = generate_token(email)

    # make sure we are on the testing sheet
    worksheet_title = wks.title
    assert worksheet_title == "MEMBERS_FOR_TESTING", "YOU ARE ON PROD WHAT THE FUCK"

    wks.delete_rows(2)
    with client.application.app_context():
        event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
        event_name = event_obj.name
        event_wks = sh.worksheet(event_name)
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
                "secondary_email": "bro@bro.com",
                "confirm_secondary": "bro@bro.com",
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
