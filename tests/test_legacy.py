from bs4 import BeautifulSoup

from project.utils.token import generate_token
from project.models import edit_form, event

def test_email_form(client):
    email = "avashraj328@gmail.com"
    token = generate_token(email)

    csrf_token = ""

    # First, make a GET request to the form to get the CSRF token.
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
                "event_Test Question 1": "question1 answer",
                "event_Test Question 2": "question2 answer",
                "event_tickets": "Test ticket 2",
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

    # add event fields to form data
    # with client.application.app_context():
    #     event_obj = event.query.filter_by(live=True).order_by(event.id.desc()).first()
    #     fields =


    # Send POST form data
    with client as c:
        response = c.post(f"/membership/full-registration/{token}", data=form_data, follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        print(soup.prettify())
        # Check if the receipt page was rendered by looking for its heading.
        heading = soup.find("h1", string="I2G Membership Completed")
        input = soup.find("input", {"name": "first_name"})
        assert not input, "The form has been rerendered"
        assert heading is not None, "The receipt page was not rendered. The registration may have failed."
