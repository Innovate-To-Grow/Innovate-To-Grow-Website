def make_sure(
    can_update: bool,
    wks_records: list[dict],
    current_user_row: int,
    new_primary_email: str,
    new_secondary_email: str
):
    """
    Validates email changes for event registration updates.
    
    Checks if the new primary/secondary emails conflict with existing users.
    If conflicts exist with expired emails, clears them and sends notifications.
    If conflicts exist with active emails, blocks the update.
    
    Args:
        can_update: Initial state (should be True)
        wks_records: List of user records from worksheet
        current_user_row: Row number of the user making the update
        new_primary_email: New primary email the user wants
        new_secondary_email: New secondary email the user wants
        
    Returns:
        tuple: (can_update, cells_to_update, emails_to_send)
            - can_update: bool - whether the update should proceed
            - cells_to_update: list - cell updates to clear expired emails  
            - emails_to_send: list - notification emails to send
    """
    cells_to_update = []
    emails_to_send = []
    
    # Define the validation matrix: (email_to_check, column_to_search)
    validations = [
        (new_primary_email, "Primary Email"),    # search_prim_in_prim_col  
        (new_primary_email, "Secondary Email"),  # search_prim_in_sec_col
        (new_secondary_email, "Primary Email"),  # search_sec_in_prim_col
        (new_secondary_email, "Secondary Email") # search_sec_in_sec_col
    ]
    
    for email_to_check, column_to_search in validations:
        # Find existing user with this email in this column
        matching_users = [row for row in wks_records if row[column_to_search] == email_to_check]
        
        if not matching_users:
            continue  # No conflict, move to next validation
            
        existing_user = matching_users[0]  # Take first match
        existing_user_row = existing_user["Row"]
        
        # Skip if this is the same user (no conflict with yourself)
        if existing_user_row == current_user_row:
            continue
            
        # Determine the verification status field based on column
        if column_to_search == "Primary Email":
            expired_field = "Primary Expired"
            verified_field = "Primary Verified" 
            other_email_field = "Secondary Email"
            other_verified_field = "Secondary Verified"
            email_being_cleared = existing_user["Primary Email"]
        else:  # Secondary Email
            expired_field = "Secondary Expired"
            verified_field = "Secondary Verified"
            other_email_field = "Primary Email" 
            other_verified_field = "Primary Verified"
            email_being_cleared = existing_user["Secondary Email"]
            
        # Check if the conflicting email is expired
        if existing_user[expired_field] == "FALSE":
            # Email is still active - block the update
            can_update = False
            
        elif existing_user[expired_field] == "TRUE":
            # Email is expired - we can claim it
            # Add cell update to clear the expired email
            cells_to_update.append({
                "row": existing_user_row,
                "column": column_to_search,
                "value": ""  # Clear the email
            })
            
            # Send notification email if the user has another verified email
            other_email = existing_user[other_email_field]
            if other_email != "" and existing_user[other_verified_field] == "TRUE":
                emails_to_send.append({
                    "to": other_email,
                    "type": "deletion_notice",
                    "user_first_name": existing_user["First Name"],
                    "user_last_name": existing_user["Last Name"], 
                    "deleted_email": email_being_cleared
                })
    
    return can_update, cells_to_update, emails_to_send
