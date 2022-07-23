import gspread
from project.models import member_roster
from flask_login import login_required, login_user, current_user
from datetime import timedelta

sa = gspread.service_account()
sh = sa.open("I2G-Master-People")

wks = sh.worksheet("double-email-test")

cols = wks.col_values(1)
cell_find = wks.find("afatali@ucmerced.edu", in_column=5)
user = wks.row_values(cell_find.row)
# cell_row_find = cell_find.row
# wks.update_cell(cell_row_find, 6, "Y")

user_object = member_roster(id=user[0],
                            first_name=user[1],
                            last_name=user[2],
                            primary_email=user[3],
                            secondary_email=user[4],
                            primary_email_status=user[5],
                            secondary_email_status=user[6],
                            info_completed=user[7],
                            organization=user[8],
                            phonenumber=user[9],
                            titlerole=user[10]
                            )
                            
login_user(user_object, remember=True)

print(current_user.titlerole)


