import os
from datetime import datetime

from gspread import Worksheet

from project import logs, tz


class Logger():
    def __init__(self):
        self.logging_sheet: Worksheet = logs

    def log_email_submission(self,
                             path: str,
                             email: str
                             ):
        order = int(self.logging_sheet.col_values(1)[-1]) + 1 if self.logging_sheet.col_values(1)[-1].isdigit() else 1
        row = [
            order, path, str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")),
            "Email: " + email
        ]
        self.logging_sheet.append_row(row)

    def log_event_register(self,
                           path: str,
                           first_name: str,
                           last_name: str,
                           primary_email: str,
                           secondary_email: str
                           ):
        order = int(self.logging_sheet.col_values(1)[-1]) + 1 if self.logging_sheet.col_values(1)[-1].isdigit() else 1
        row = [
            order, path, str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")),
            "First Name: " + first_name,
            "Last Name: " + last_name, "Primary Email: " + primary_email, "Secondary Email: " + secondary_email
        ]
        self.logging_sheet.append_row(row)

    def log_registration(self, path, first_name, last_name, primary_email, secondary_email):
        order = int(self.logging_sheet.col_values(1)[-1]) + 1 if self.logging_sheet.col_values(1)[-1].isdigit() else 1
        row = [
            order, path, str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")),
            "First Name: " + first_name, "Last Name: " + last_name,
            "Primary Email: " + primary_email, "Secondary Email: " + secondary_email
        ]
        self.logging_sheet.append_row(row)

    def log_update(self, path, first_name, last_name, primary_email, secondary_email):
        order = int(self.logging_sheet.col_values(1)[-1]) + 1 if self.logging_sheet.col_values(1)[-1].isdigit() else 1
        row = [
            order, path, str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")),
            "First Name: " + first_name, "Last Name: " + last_name,
            "Primary Email: " + primary_email, "Secondary Email: " + secondary_email
        ]
        self.logging_sheet.append_row(row)

    def log_complete_registration(self, path, first_name, last_name, primary_email, secondary_email, phone_number="",
                                  register_event="No Event"):
        order = int(self.logging_sheet.col_values(1)[-1]) + 1 if self.logging_sheet.col_values(1)[-1].isdigit() else 1
        phone_info = f"Phone: {phone_number}" if phone_number else "No Phone"
        row = [
            order, path, str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")),
            "First Name: " + first_name, "Last Name: " + last_name,
            "Primary Email: " + primary_email, "Secondary Email: " + secondary_email,
            phone_info, register_event
        ]
        self.logging_sheet.append_row(row)

    def log_background_error(self, route: str, user_email: str, error_details: dict):
        """Log background thread errors with full stack traces"""
        order = int(self.logging_sheet.col_values(1)[-1]) + 1 if self.logging_sheet.col_values(1)[-1].isdigit() else 1

        # Format stack trace (Sheets supports multi-line text)
        stack_trace = error_details.get('stack_trace', 'No stack trace available')

        row = [
            order,
            route,
            str(datetime.now(tz).strftime("%Y-%m-%d %I:%M %p")),
            "BACKGROUND_ERROR",
            f"User: {user_email}",
            error_details.get('error_type', 'Unknown'),
            error_details.get('error_message', 'No message'),
            stack_trace  # Full multi-line stack trace
        ]
        self.logging_sheet.append_row(row)
