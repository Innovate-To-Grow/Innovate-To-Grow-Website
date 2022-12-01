import time
from project import wks
from project.utils.index_helper import wks_indices, arr_indices

def expiry_timer(email, email_col, verif_col):
    wks_idx = wks_indices()
    
    user = wks.find(email, in_column=wks_idx[email_col])
    row = user.row

    time.sleep(90)
    if wks.cell(row, wks_idx[verif_col]).value == "FALSE":
        if verif_col == "Primary Verified":
            wks.update_cell(row, wks_idx["Primary Expired"], "TRUE")
        elif verif_col == "Secondary Verified":
            wks.update_cell(row, wks_idx["Secondary Expired"], "TRUE")
