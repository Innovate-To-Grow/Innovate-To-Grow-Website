import email
import gspread
from project.models import member_roster
from flask_login import login_required, login_user, current_user
from datetime import timedelta

sa = gspread.service_account("service_account.json")
sh = sa.open("I2G-Master-People")

wks = sh.worksheet("double-email-test")

email_list = []

for i in range(2, wks.row_count + 1):
    user = wks.row_values(i)
    if user[11] == "TRUE":
        email_list.append(str(user[3]))
    if user[12] == "TRUE":
        email_list.append(str(user[4]))
    
            
print(email_list) 