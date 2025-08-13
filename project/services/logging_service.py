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

    def log(self,
        path: str,
        email: str):
        order = int(self.logging_sheet.col_values(1)[-1]) + 1 if self.logging_sheet.col_values(1)[-1].isdigit() else 1
        row = [
            order, path, str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")), "Email: " + email
        ]
        self.logging_sheet.append_row(row)
