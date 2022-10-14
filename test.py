import time
from werkzeug.datastructures import MultiDict
from multiprocessing import Process
from project import wks
from gspread import cell

user_prim1 = wks.find("pissergah3@gmail.com", in_column=6)

print(wks.row_values(user_prim1.row)[7])