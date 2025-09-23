# """
# Unit Tests for Registration Utils Pure Logic Functions

# Tests for analyze_user_existence_check() and analyze_complete_registration_conflicts()
# These are pure function tests with no side effects or mocking required.
# """

# import pytest
# from project.utils.registration_utils import (
#     analyze_user_existence_check,
#     analyze_complete_registration_conflicts,
#     CompleteRegistrationDecision
# )


# class TestAnalyzeUserExistenceCheck:
#     """Test cases for analyze_user_existence_check() function"""

#     def test_user_doesnt_exist_empty_database(self):
#         """Test with empty database - no existing users"""
#         wks_records = []
#         primary_email = "new@example.com"
#         secondary_email = "secondary@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is False
#         assert result["existing_user"] is None
#         assert result["primary_email_matches"] == []
#         assert result["secondary_email_matches"] == []
#         assert result["should_use_complete_registration"] is True
#         assert result["should_redirect_to_update"] is False

#     def test_user_doesnt_exist_unique_emails(self):
#         """Test with existing users but unique emails"""
#         wks_records = [
#             {
#                 "Row": 1,
#                 "Primary Email": "existing1@example.com",
#                 "Secondary Email": "existing2@example.com",
#                 "First Name": "John",
#                 "Last Name": "Doe"
#             },
#             {
#                 "Row": 2,
#                 "Primary Email": "other1@example.com",
#                 "Secondary Email": "other2@example.com",
#                 "First Name": "Jane",
#                 "Last Name": "Smith"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "unique@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is False
#         assert result["existing_user"] is None
#         assert result["primary_email_matches"] == []
#         assert result["secondary_email_matches"] == []
#         assert result["should_use_complete_registration"] is True
#         assert result["should_redirect_to_update"] is False

#     def test_user_exists_primary_matches_existing_primary(self):
#         """Test primary email matches existing user's primary email"""
#         wks_records = [
#             {
#                 "Row": 1,
#                 "Primary Email": "john@example.com",
#                 "Secondary Email": "john.secondary@example.com",
#                 "First Name": "John",
#                 "Last Name": "Doe"
#             }
#         ]
#         primary_email = "john@example.com"
#         secondary_email = "new.secondary@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is True
#         assert result["existing_user"]["Row"] == 1
#         assert len(result["primary_email_matches"]) == 1
#         assert result["primary_email_matches"][0]["found_in"] == "Primary Email"
#         assert result["secondary_email_matches"] == []
#         assert result["should_use_complete_registration"] is False
#         assert result["should_redirect_to_update"] is True

#     def test_user_exists_primary_matches_existing_secondary(self):
#         """Test primary email matches existing user's secondary email"""
#         wks_records = [
#             {
#                 "Row": 2,
#                 "Primary Email": "jane@example.com",
#                 "Secondary Email": "matching@example.com",
#                 "First Name": "Jane",
#                 "Last Name": "Smith"
#             }
#         ]
#         primary_email = "matching@example.com"
#         secondary_email = "new@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is True
#         assert result["existing_user"]["Row"] == 2
#         assert len(result["primary_email_matches"]) == 1
#         assert result["primary_email_matches"][0]["found_in"] == "Secondary Email"
#         assert result["secondary_email_matches"] == []
#         assert result["should_use_complete_registration"] is False
#         assert result["should_redirect_to_update"] is True

#     def test_user_exists_secondary_matches_existing_primary(self):
#         """Test secondary email matches existing user's primary email"""
#         wks_records = [
#             {
#                 "Row": 3,
#                 "Primary Email": "existing@example.com",
#                 "Secondary Email": "other@example.com",
#                 "First Name": "Bob",
#                 "Last Name": "Wilson"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "existing@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is True
#         assert result["existing_user"]["Row"] == 3
#         assert result["primary_email_matches"] == []
#         assert len(result["secondary_email_matches"]) == 1
#         assert result["secondary_email_matches"][0]["found_in"] == "Primary Email"
#         assert result["should_use_complete_registration"] is False
#         assert result["should_redirect_to_update"] is True

#     def test_user_exists_secondary_matches_existing_secondary(self):
#         """Test secondary email matches existing user's secondary email"""
#         wks_records = [
#             {
#                 "Row": 4,
#                 "Primary Email": "primary@example.com",
#                 "Secondary Email": "secondary@example.com",
#                 "First Name": "Alice",
#                 "Last Name": "Johnson"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "secondary@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is True
#         assert result["existing_user"]["Row"] == 4
#         assert result["primary_email_matches"] == []
#         assert len(result["secondary_email_matches"]) == 1
#         assert result["secondary_email_matches"][0]["found_in"] == "Secondary Email"
#         assert result["should_use_complete_registration"] is False
#         assert result["should_redirect_to_update"] is True

#     def test_both_emails_exist_different_users(self):
#         """Test both emails exist but belong to different users"""
#         wks_records = [
#             {
#                 "Row": 1,
#                 "Primary Email": "user1@example.com",
#                 "Secondary Email": "user1.sec@example.com",
#                 "First Name": "User",
#                 "Last Name": "One"
#             },
#             {
#                 "Row": 2,
#                 "Primary Email": "user2@example.com",
#                 "Secondary Email": "user2.sec@example.com",
#                 "First Name": "User",
#                 "Last Name": "Two"
#             }
#         ]
#         primary_email = "user1@example.com"
#         secondary_email = "user2.sec@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is True
#         assert result["existing_user"]["Row"] == 1  # First match found
#         assert len(result["primary_email_matches"]) == 1
#         assert len(result["secondary_email_matches"]) == 1
#         assert result["should_use_complete_registration"] is False
#         assert result["should_redirect_to_update"] is True

#     def test_both_emails_same_user(self):
#         """Test both emails belong to same existing user"""
#         wks_records = [
#             {
#                 "Row": 5,
#                 "Primary Email": "same.user@example.com",
#                 "Secondary Email": "same.user.secondary@example.com",
#                 "First Name": "Same",
#                 "Last Name": "User"
#             }
#         ]
#         primary_email = "same.user@example.com"
#         secondary_email = "same.user.secondary@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is True
#         assert result["existing_user"]["Row"] == 5
#         assert len(result["primary_email_matches"]) == 1
#         assert len(result["secondary_email_matches"]) == 1
#         assert result["should_use_complete_registration"] is False
#         assert result["should_redirect_to_update"] is True

#     def test_multiple_matches_same_email(self):
#         """Test email appears in multiple user records (data consistency issue)"""
#         wks_records = [
#             {
#                 "Row": 1,
#                 "Primary Email": "duplicate@example.com",
#                 "Secondary Email": "first.secondary@example.com",
#                 "First Name": "First",
#                 "Last Name": "User"
#             },
#             {
#                 "Row": 2,
#                 "Primary Email": "other@example.com",
#                 "Secondary Email": "duplicate@example.com",
#                 "First Name": "Second",
#                 "Last Name": "User"
#             }
#         ]
#         primary_email = "duplicate@example.com"
#         secondary_email = "new@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         assert result["user_exists"] is True
#         assert result["existing_user"]["Row"] == 1  # First match found
#         assert len(result["primary_email_matches"]) == 2  # Found in both places
#         assert result["secondary_email_matches"] == []
#         assert result["should_use_complete_registration"] is False
#         assert result["should_redirect_to_update"] is True

#     def test_case_sensitivity_handling(self):
#         """Test case sensitivity in email matching"""
#         wks_records = [
#             {
#                 "Row": 1,
#                 "Primary Email": "test@email.com",
#                 "Secondary Email": "secondary@email.com",
#                 "First Name": "Test",
#                 "Last Name": "User"
#             }
#         ]
#         primary_email = "TEST@EMAIL.COM"
#         secondary_email = "new@example.com"

#         result = analyze_user_existence_check(wks_records, primary_email, secondary_email)

#         # Should find match despite case difference
#         assert result["user_exists"] is True
#         assert result["existing_user"]["Row"] == 1


# class TestAnalyzeCompleteRegistrationConflicts:
#     """Test cases for analyze_complete_registration_conflicts() function"""

#     def test_no_conflicts_empty_database(self):
#         """Test with empty database - no conflicts possible"""
#         wks_records = []
#         primary_email = "new@example.com"
#         secondary_email = "secondary@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert isinstance(result, CompleteRegistrationDecision)
#         assert result.can_proceed is True
#         assert result.emails_to_clear == []
#         assert result.notification_emails == []
#         assert result.conflict_details["secondary_conflicts"] == []

#     def test_no_conflicts_unique_emails(self):
#         """Test with existing users but no conflicts with secondary email"""
#         wks_records = [
#             {
#                 "Row": 1,
#                 "Primary Email": "existing1@example.com",
#                 "Secondary Email": "existing2@example.com",
#                 "Primary Expired": "FALSE",
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "TRUE",
#                 "Secondary Verified": "TRUE",
#                 "First Name": "John",
#                 "Last Name": "Doe"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "unique@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is True
#         assert result.emails_to_clear == []
#         assert result.notification_emails == []
#         assert result.conflict_details["secondary_conflicts"] == []

#     def test_secondary_conflicts_with_expired_primary_clearable(self):
#         """Test secondary email conflicts with expired primary - should be clearable"""
#         wks_records = [
#             {
#                 "Row": 2,
#                 "Primary Email": "conflict@example.com",  # This will conflict with secondary
#                 "Secondary Email": "other@example.com",
#                 "Primary Expired": "TRUE",  # Expired - can be cleared
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "FALSE",
#                 "Secondary Verified": "TRUE",
#                 "Primary Bounced": "",
#                 "Secondary Bounced": "",
#                 "First Name": "Existing",
#                 "Last Name": "User"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "conflict@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is True
#         assert len(result.emails_to_clear) == 1
#         assert result.emails_to_clear[0] == {
#             "row": 2,
#             "column": "Primary Email",
#             "value": ""
#         }
#         assert len(result.notification_emails) == 1
#         assert result.notification_emails[0]["to"] == "other@example.com"
#         assert result.notification_emails[0]["type"] == "deletion_notice"
#         assert result.notification_emails[0]["deleted_email"] == "conflict@example.com"

#         conflicts = result.conflict_details["secondary_conflicts"]
#         assert len(conflicts) == 1
#         assert conflicts[0]["action"] == "cleared"
#         assert conflicts[0]["conflicting_email"] == "conflict@example.com"

#     def test_secondary_conflicts_with_expired_secondary_clearable(self):
#         """Test secondary email conflicts with expired secondary - should be clearable"""
#         wks_records = [
#             {
#                 "Row": 3,
#                 "Primary Email": "verified@example.com",
#                 "Secondary Email": "conflict@example.com",  # This will conflict
#                 "Primary Expired": "FALSE",
#                 "Secondary Expired": "TRUE",  # Expired - can be cleared
#                 "Primary Verified": "TRUE",
#                 "Secondary Verified": "FALSE",
#                 "Primary Bounced": "",
#                 "Secondary Bounced": "",
#                 "First Name": "Another",
#                 "Last Name": "User"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "conflict@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is True
#         assert len(result.emails_to_clear) == 1
#         assert result.emails_to_clear[0] == {
#             "row": 3,
#             "column": "Secondary Email",
#             "value": ""
#         }
#         assert len(result.notification_emails) == 1
#         assert result.notification_emails[0]["to"] == "verified@example.com"
#         assert result.notification_emails[0]["deleted_email"] == "conflict@example.com"

#     def test_secondary_conflicts_with_active_primary_blocking(self):
#         """Test secondary email conflicts with active primary - should block"""
#         wks_records = [
#             {
#                 "Row": 4,
#                 "Primary Email": "active@example.com",  # This conflicts and is active
#                 "Secondary Email": "other@example.com",
#                 "Primary Expired": "FALSE",  # Active - blocks registration
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "TRUE",
#                 "Secondary Verified": "TRUE",
#                 "First Name": "Active",
#                 "Last Name": "User"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "active@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is False
#         assert result.emails_to_clear == []
#         assert result.notification_emails == []

#         conflicts = result.conflict_details["secondary_conflicts"]
#         assert len(conflicts) == 1
#         assert conflicts[0]["action"] == "blocked"
#         assert conflicts[0]["expired_status"] == "FALSE"

#     def test_secondary_conflicts_with_active_secondary_blocking(self):
#         """Test secondary email conflicts with active secondary - should block"""
#         wks_records = [
#             {
#                 "Row": 5,
#                 "Primary Email": "primary@example.com",
#                 "Secondary Email": "active@example.com",  # This conflicts and is active
#                 "Primary Expired": "FALSE",
#                 "Secondary Expired": "FALSE",  # Active - blocks registration
#                 "Primary Verified": "TRUE",
#                 "Secondary Verified": "TRUE",
#                 "First Name": "Another",
#                 "Last Name": "Active"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "active@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is False
#         assert result.emails_to_clear == []
#         assert result.notification_emails == []

#         conflicts = result.conflict_details["secondary_conflicts"]
#         assert len(conflicts) == 1
#         assert conflicts[0]["action"] == "blocked"
#         assert conflicts[0]["column"] == "Secondary Email"

#     def test_multiple_expired_conflicts(self):
#         """Test secondary email appears in multiple expired records"""
#         wks_records = [
#             {
#                 "Row": 6,
#                 "Primary Email": "conflict@example.com",  # First conflict
#                 "Secondary Email": "other1@example.com",
#                 "Primary Expired": "TRUE",
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "FALSE",
#                 "Secondary Verified": "TRUE",
#                 "Primary Bounced": "",
#                 "Secondary Bounced": "",
#                 "First Name": "First",
#                 "Last Name": "Conflict"
#             },
#             {
#                 "Row": 7,
#                 "Primary Email": "other2@example.com",
#                 "Secondary Email": "conflict@example.com",  # Second conflict
#                 "Primary Expired": "FALSE",
#                 "Secondary Expired": "TRUE",
#                 "Primary Verified": "TRUE",
#                 "Secondary Verified": "FALSE",
#                 "Primary Bounced": "",
#                 "Secondary Bounced": "",
#                 "First Name": "Second",
#                 "Last Name": "Conflict"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "conflict@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is True
#         assert len(result.emails_to_clear) == 2

#         # Check both conflicts are cleared
#         rows_cleared = [clear["row"] for clear in result.emails_to_clear]
#         assert 6 in rows_cleared
#         assert 7 in rows_cleared

#         # Check both notifications are sent
#         assert len(result.notification_emails) == 2
#         notification_emails = [notif["to"] for notif in result.notification_emails]
#         assert "other1@example.com" in notification_emails
#         assert "other2@example.com" in notification_emails

#         # Check conflict details
#         conflicts = result.conflict_details["secondary_conflicts"]
#         assert len(conflicts) == 2

#     def test_mixed_conflicts_active_blocks_registration(self):
#         """Test mix of expired (clearable) and active (blocking) conflicts - should block"""
#         wks_records = [
#             {
#                 "Row": 8,
#                 "Primary Email": "conflict@example.com",  # Expired - would be clearable
#                 "Secondary Email": "other1@example.com",
#                 "Primary Expired": "TRUE",
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "FALSE",
#                 "Secondary Verified": "TRUE",
#                 "First Name": "Expired",
#                 "Last Name": "User"
#             },
#             {
#                 "Row": 9,
#                 "Primary Email": "other2@example.com",
#                 "Secondary Email": "conflict@example.com",  # Active - blocks
#                 "Primary Expired": "FALSE",
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "TRUE",
#                 "Secondary Verified": "TRUE",
#                 "First Name": "Active",
#                 "Last Name": "User"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "conflict@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is False  # Active conflict blocks everything
#         assert result.emails_to_clear == []
#         assert result.notification_emails == []

#         conflicts = result.conflict_details["secondary_conflicts"]
#         assert len(conflicts) == 2
#         actions = [conflict["action"] for conflict in conflicts]
#         # All conflicts should be blocked when ANY conflict is active
#         assert all(action == "blocked" for action in actions)

#     def test_expired_with_unverified_other_email_no_notification(self):
#         """Test expired conflict but other email is unverified - no notification sent"""
#         wks_records = [
#             {
#                 "Row": 10,
#                 "Primary Email": "conflict@example.com",
#                 "Secondary Email": "unverified@example.com",
#                 "Primary Expired": "TRUE",
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "FALSE",
#                 "Secondary Verified": "FALSE",  # Unverified - no notification
#                 "First Name": "No",
#                 "Last Name": "Notification"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "conflict@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is True
#         assert len(result.emails_to_clear) == 1
#         assert result.notification_emails == []  # No verified email to notify

#     def test_expired_with_empty_other_email_no_notification(self):
#         """Test expired conflict but other email is empty - no notification sent"""
#         wks_records = [
#             {
#                 "Row": 11,
#                 "Primary Email": "conflict@example.com",
#                 "Secondary Email": "",  # Empty - no notification
#                 "Primary Expired": "TRUE",
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "FALSE",
#                 "Secondary Verified": "FALSE",
#                 "First Name": "Empty",
#                 "Last Name": "Secondary"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "conflict@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is True
#         assert len(result.emails_to_clear) == 1
#         assert result.notification_emails == []

#     def test_empty_secondary_email_no_conflicts(self):
#         """Test with empty secondary email - no conflicts possible"""
#         wks_records = [
#             {
#                 "Row": 12,
#                 "Primary Email": "existing@example.com",
#                 "Secondary Email": "other@example.com",
#                 "Primary Expired": "FALSE",
#                 "Secondary Expired": "FALSE",
#                 "First Name": "Existing",
#                 "Last Name": "User"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = ""  # Empty secondary

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         assert result.can_proceed is True
#         assert result.emails_to_clear == []
#         assert result.notification_emails == []
#         assert result.conflict_details["secondary_conflicts"] == []

#     def test_case_sensitivity_in_conflicts(self):
#         """Test case sensitivity handling in conflict detection"""
#         wks_records = [
#             {
#                 "Row": 13,
#                 "Primary Email": "test@example.com",
#                 "Secondary Email": "other@example.com",
#                 "Primary Expired": "TRUE",
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "FALSE",
#                 "Secondary Verified": "TRUE",
#                 "First Name": "Case",
#                 "Last Name": "Test"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "TEST@EXAMPLE.COM"  # Different case

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         # Should detect conflict despite case difference
#         assert result.can_proceed is True
#         assert len(result.emails_to_clear) == 1
#         assert len(result.notification_emails) == 1

#     def test_conflict_details_structure(self):
#         """Test that conflict_details contains all expected information"""
#         wks_records = [
#             {
#                 "Row": 14,
#                 "Primary Email": "conflict@example.com",
#                 "Secondary Email": "notify@example.com",
#                 "Primary Expired": "TRUE",
#                 "Secondary Expired": "FALSE",
#                 "Primary Verified": "FALSE",
#                 "Secondary Verified": "TRUE",
#                 "Primary Bounced": "",
#                 "Secondary Bounced": "",
#                 "First Name": "Detail",
#                 "Last Name": "Test"
#             }
#         ]
#         primary_email = "new@example.com"
#         secondary_email = "conflict@example.com"

#         result = analyze_complete_registration_conflicts(wks_records, primary_email, secondary_email)

#         conflicts = result.conflict_details["secondary_conflicts"]
#         assert len(conflicts) == 1

#         conflict = conflicts[0]
#         assert "existing_user_row" in conflict
#         assert "existing_user_name" in conflict
#         assert "conflicting_email" in conflict
#         assert "column" in conflict
#         assert "expired_status" in conflict
#         assert "verified_status" in conflict
#         assert "action" in conflict

#         assert conflict["existing_user_row"] == 14
#         assert conflict["existing_user_name"] == "Detail Test"
#         assert conflict["conflicting_email"] == "conflict@example.com"
#         assert conflict["column"] == "Primary Email"
#         assert conflict["action"] == "cleared"
