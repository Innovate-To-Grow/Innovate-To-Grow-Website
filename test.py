import time
from multiprocessing import Process
from project import wks

def delete_email(value, row, col, email):
    time.sleep(value)
    user = wks.find(email, in_column=col)
    user = wks.row_values(user.row)
    print(user[col+1])
    if user[col+1] == "TRUE":
        print("here")
        return
    else:
        print("there")
        wks.update_cell(row,col,"")

user_prim1 = wks.find("alvin.toto258@gmail.com", in_column=6)
row_prim1 = user_prim1.row
user_prim1 = wks.row_values(row_prim1)
delete_email(5, row_prim1, 6, user_prim1[5])