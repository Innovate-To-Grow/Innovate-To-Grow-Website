import time
from project import wks
from project.util.token import generate_token, confirm_token, confirm_token_no_expiry

# token = generate_token("anjello10fat@gmail.com")

# print(token)
# print(confirm_token(token))
# print(confirm_token_no_expiry(token))
user_sec2 = wks.find("afatali@ucmerced.edu", in_column=6)
if user_sec2 is not None:
    row_sec2 = user_sec2.row
    user_sec2 = wks.row_values(row_sec2)

print(row_sec2)
# def delete_email(value):
#     time.sleep(value)
#     wks.update_cell(2,6,"WORKEDEDEDEDEDDDDDD")

# delete_email(10)


# import gspread
# wks = gspread.service_account().open("I2G-Master-People").worksheet("double-email-test")
# form_row = wks.row_values(1)
# form_size = len(form_row)
# data = []
# for x in range(12, form_size):
#     data.append(form_row[x])
# print(data)

