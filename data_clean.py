import gspread
from gspread.client import BackoffClient
from gspread.cell import Cell

gc = gspread.service_account(client_factory=BackoffClient)
sh = gc.open("I2G Membership")
wks = sh.worksheet("Members")

def get_wks_records(wks):
    wks_records = wks.get_all_records()
    for i, row in enumerate(wks_records, start=2):
        row['Row'] = i
    return wks_records


def get_wks_columns(wks):
    header_row = wks.row_values(1)
    wks_columns = {header_row[i]: i+1 for i in range(len(header_row))}
    return wks_columns


cells = []

# make everything in the "Primary Email" column lowercase
wks_records = get_wks_records(wks)
wks_columns = get_wks_columns(wks)

for row in wks_records:
    cells.append(Cell(row['Row'], wks_columns['Primary Email'], row['Primary Email'].lower()))

wks.update_cells(cells)

cells.clear()

wks_records = get_wks_records(wks)
wks_columns = get_wks_columns(wks)

# remove whitespace from the "Primary Email" column
for row in wks_records:
    cells.append(Cell(row['Row'], wks_columns['Primary Email'], row['Primary Email'].strip()))

wks.update_cells(cells)
