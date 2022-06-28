import gspread

sa = gspread.service_account()
sh = sa.open("I2G-Master-People")

wks = sh.worksheet("double-email-test")

cols = wks.col_values(1)
cell_find = wks.find("alvin.toto258@gmail.com")
cell_row_find = cell_find.row
wks.update_cell(cell_row_find, 6, "Y")


