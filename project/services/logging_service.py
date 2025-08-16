import os
from datetime import datetime

from dotenv import load_dotenv
from gspread import Worksheet

from project import dev_logs, logs, tz

load_dotenv()

class Logger():
    def __init__(self):
        self.mode = os.getenv("MODE")

        if self.mode == "DEV":
            self.logging_sheet: Worksheet = dev_logs
        else:
            self.logging_sheet: Worksheet = logs

    def log_email_submission(self,
        path: str,
        email: str
    ):
        order = int(self.logging_sheet.col_values(1)[-1]) + 1 if self.logging_sheet.col_values(1)[-1].isdigit() else 1
        row = [
            order, path, str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")), "Email: " + email
        ]
        self.logging_sheet.append_row(row)

    def log_event_register(self,
        path: str,
        first_name: str,
        last_name: str,
        primary_email: str,
        secondary_email: str
    ):
        order = int(logs.col_values(1)[-1]) + 1 if logs.col_values(1)[-1].isdigit() else 1
        row = [
            order, "/event-registration/<event_name>/<token>", str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")), "First Name: " + first_name,
            "Last Name: " + last_name, "Primary Email: " + primary_email, "Secondary Email: " + secondary_email
        ]
        logs.append_row(row)
