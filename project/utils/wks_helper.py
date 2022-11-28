from project import wks

def wks_column(column_name):
    return wks.find(column_name, in_row=1).col

def arr_column(column_name):
    return wks_column(column_name) - 1