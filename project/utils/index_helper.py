def wks_indices(wks):
    dict = {}
    counter = 1
    row_values = wks.row_values(1)
    
    for value in row_values:
        dict[value] = counter
        counter += 1

    return dict


def arr_indices(wks):
    dict = {}
    counter = 0
    row_values = wks.row_values(1)
    
    for value in row_values:
        dict[value] = counter
        counter += 1

    return dict