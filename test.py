# from project.util.token import generate_token, confirm_token, confirm_token_no_expiry

# token = generate_token("missingbeatrice")

# print(confirm_token(token))
# print(confirm_token_no_expiry(token))
import gspread
wks = gspread.service_account().open("I2G-Master-People").worksheet("double-email-test")
form_row = wks.row_values(1)
form_size = len(form_row)
data = []
for x in range(12, form_size):
    data.append(form_row[x])
print(data)