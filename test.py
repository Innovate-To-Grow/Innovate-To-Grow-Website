import time
from werkzeug.datastructures import MultiDict
from multiprocessing import Process
from project import wks
from gspread import cell

s = "i like asian girls"
a = s.split()
a.insert(0, "")

print(a)