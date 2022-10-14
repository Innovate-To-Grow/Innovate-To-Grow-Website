import time
from werkzeug.datastructures import MultiDict
from multiprocessing import Process
from project import wks
from gspread import cell

user_sec2 = wks.find("ato258@ucmerced.edu", in_column=7)
new = wks.row_values(user_sec2.row)[8]

print(user_sec2.row)