from gspread import Worksheet

from project import get_wks_records
from project.models import edit_form, event

def clear_members_sheet(wks: Worksheet):
    """ Clears the testing members sheet

    Args:
        wks (Worksheet): testing members sheet
    """
    records = get_wks_records(wks)
    num_records = len(records)
    if num_records > 1:
        wks.delete_rows(2, num_records + 1)
    elif num_records > 0:
        wks.delete_rows(2)


def get_event_info(client):
    """ Gets the name, ticket, and the question answers
    for an event

    Args:
        client - fake version of the flask app used for testing

    Returns:
        event_name - name of event
        ticket - the ticket the testing client will choose for the event
        questions (dict) - the question as keys and answers as values for the questions
        on the given event

    """
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

    return event_name, ticket, questions, base_answer


def clear_event_sheet(sh, event_name):
    """ Clear the event wks

    Args:
        sh - the sheet object where we get the correct sheet
        event_name - the name of the event
    """
    event_wks = sh.worksheet(event_name)
    event_records = get_wks_records(event_wks)
    num_event_records = len(event_records)
    if num_event_records > 1:
        event_wks.delete_rows(2, num_event_records)
    elif num_event_records > 0:
        event_wks.delete_rows(2)

    return event_wks
