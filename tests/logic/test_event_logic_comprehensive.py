# import pytest
# from project.utils.event_utils import make_sure
# from project.utils.event_utils import analyze_email_changes, EmailChangeDecision


# @pytest.fixture
# def sample_user_data():
#     """Sample user data representing current state of worksheet"""
#     return [
#         {
#             "Order": 1,
#             "First Name": "Alice",
#             "Last Name": "Smith",
#             "Primary Email": "alice@example.com",
#             "Primary Verified": "TRUE",
#             "Primary Subscribed": "TRUE",
#             "Primary Expired": "FALSE",
#             "Secondary Email": "alice.secondary@example.com",
#             "Secondary Verified": "TRUE",
#             "Secondary Subscribed": "TRUE",
#             "Secondary Expired": "FALSE",
#             "Row": 2,
#         },
#         {
#             "Order": 2,
#             "First Name": "Bob",
#             "Last Name": "Jones",
#             "Primary Email": "bob@example.com",
#             "Primary Verified": "TRUE",
#             "Primary Subscribed": "TRUE",
#             "Primary Expired": "FALSE",
#             "Secondary Email": "bob.secondary@example.com",
#             "Secondary Verified": "FALSE",
#             "Secondary Subscribed": "FALSE",
#             "Secondary Expired": "FALSE",
#             "Row": 3,
#         },
#         {
#             "Order": 3,
#             "First Name": "Charlie",
#             "Last Name": "Brown",
#             "Primary Email": "charlie@example.com",
#             "Primary Verified": "FALSE",
#             "Primary Subscribed": "FALSE",
#             "Primary Expired": "TRUE",
#             "Secondary Email": "charlie.secondary@example.com",
#             "Secondary Verified": "TRUE",
#             "Secondary Subscribed": "TRUE",
#             "Secondary Expired": "FALSE",
#             "Row": 4,
#         }
#     ]


# class TestEventValidation:
#     """Test the four validation scenarios for email conflicts"""

#     def test_happy_path_no_conflicts(self, sample_user_data):
#         """User keeps their existing emails - no conflicts"""
#         current_user_row = 2  # Alice's row
#         new_primary = "alice@example.com"  # Same as current
#         new_secondary = "alice.secondary@example.com"  # Same as current

#         can_update, cells, emails = make_sure(
#             True, sample_user_data, current_user_row, new_primary, new_secondary
#         )

#         assert can_update == True
#         assert cells == []
#         assert emails == []

#     def test_primary_email_conflict_expired(self, sample_user_data):
#         """User tries to claim an expired email - should succeed"""
#         current_user_row = 2  # Alice's row
#         new_primary = "charlie@example.com"  # Charlie's expired email
#         new_secondary = "alice.secondary@example.com"

#         can_update, cells, emails = make_sure(
#             True, sample_user_data, current_user_row, new_primary, new_secondary
#         )

#         assert can_update == True
#         # Should clear Charlie's email and send notification
#         assert len(cells) == 1  # Clear charlie@example.com from row 4
#         assert len(emails) == 1  # Notify Charlie's secondary email

#     def test_primary_email_conflict_active(self, sample_user_data):
#         """User tries to claim an active email - should fail"""
#         current_user_row = 2  # Alice's row
#         new_primary = "bob@example.com"  # Bob's active email
#         new_secondary = "alice.secondary@example.com"

#         can_update, cells, emails = make_sure(
#             True, sample_user_data, current_user_row, new_primary, new_secondary
#         )

#         assert can_update == False  # Should block the update
#         assert cells == []
#         assert emails == []

#     def test_secondary_email_conflict_expired(self, sample_user_data):
#         """User tries to use expired email as secondary"""
#         current_user_row = 2  # Alice's row
#         new_primary = "alice@example.com"
#         new_secondary = "charlie@example.com"  # Charlie's expired email

#         can_update, cells, emails = make_sure(
#             True, sample_user_data, current_user_row, new_primary, new_secondary
#         )

#         assert can_update == True
#         assert len(cells) == 1  # Clear charlie@example.com
#         assert len(emails) == 1  # Notify Charlie

#     def test_multiple_conflicts(self, sample_user_data):
#         """User tries to claim two conflicting emails"""
#         current_user_row = 2  # Alice's row
#         new_primary = "bob@example.com"  # Bob's active email
#         new_secondary = "charlie@example.com"  # Charlie's expired email

#         can_update, cells, emails = make_sure(
#             True, sample_user_data, current_user_row, new_primary, new_secondary
#         )

#         # Should fail due to Bob's active email, even though Charlie's is available
#         assert can_update == False

#     def test_cross_column_conflicts(self, sample_user_data):
#         """User tries primary=someone's secondary, secondary=someone's primary"""
#         current_user_row = 2  # Alice's row
#         new_primary = "bob.secondary@example.com"  # Bob's secondary
#         new_secondary = "bob@example.com"  # Bob's primary

#         can_update, cells, emails = make_sure(
#             True, sample_user_data, current_user_row, new_primary, new_secondary
#         )

#         # Both are active, so should fail
#         assert can_update == False

#     def test_edge_case_same_user_email_swap(self, sample_user_data):
#         """User swaps their own primary and secondary emails"""
#         current_user_row = 2  # Alice's row
#         new_primary = "alice.secondary@example.com"  # Their current secondary
#         new_secondary = "alice@example.com"  # Their current primary

#         can_update, cells, emails = make_sure(
#             True, sample_user_data, current_user_row, new_primary, new_secondary
#         )

#         # Should succeed - user is swapping their own emails
#         assert can_update == True
#         # Should not generate conflicts since it's the same user
#         assert cells == []
#         assert emails == []

#     def test_data_integrity_duplicate_emails(self, sample_user_data):
#         """Edge case: What if data has duplicate emails (shouldn't happen but test robustness)"""
#         # Add a duplicate email to test data
#         duplicate_user = sample_user_data[0].copy()
#         duplicate_user["Row"] = 5
#         duplicate_user["Order"] = 4
#         sample_user_data.append(duplicate_user)

#         current_user_row = 3  # Bob's row
#         new_primary = "alice@example.com"  # Alice's email (now duplicated)
#         new_secondary = "bob.secondary@example.com"

#         can_update, cells, emails = make_sure(
#             True, sample_user_data, current_user_row, new_primary, new_secondary
#         )

#         # Should handle gracefully (your implementation decides how)
#         # At minimum, should not crash
#         assert isinstance(can_update, bool)
#         assert isinstance(cells, list)
#         assert isinstance(emails, list)


# class TestAnalyzeEmailChanges:
#     """Test suite for the analyze_email_changes pure function"""

#     def test_no_email_changes(self):
#         """When both emails stay the same - no changes needed"""
#         current_user = {
#             "Primary Email": "user@test.com",
#             "Secondary Email": "user2@test.com"
#         }

#         result = analyze_email_changes(current_user, "user@test.com", "user2@test.com")

#         assert result.change_type == "no_change"
#         assert result.emails_needing_verification == []
#         assert result.verification_status_updates == {"primary": False, "secondary": False}
#         assert result.subscription_updates == {"primary": None, "secondary": None}

#     def test_complete_email_swap(self):
#         """When user swaps primary and secondary emails completely"""
#         current_user = {
#             "Primary Email": "primary@test.com",
#             "Secondary Email": "secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "secondary@test.com", "primary@test.com")

#         assert result.change_type == "swap_complete"
#         assert result.emails_needing_verification == []
#         assert result.verification_status_updates == {"primary": False, "secondary": False}
#         assert result.subscription_updates == {"primary": None, "secondary": None}

#     def test_partial_swap_primary_becomes_secondary(self):
#         """When current primary becomes new secondary, new primary is completely new"""
#         current_user = {
#             "Primary Email": "old_primary@test.com",
#             "Secondary Email": "old_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "new_primary@test.com", "old_primary@test.com")

#         assert result.change_type == "swap_partial"
#         assert result.emails_needing_verification == ["new_primary@test.com"]
#         assert result.verification_status_updates == {"primary": True, "secondary": False}
#         assert result.subscription_updates == {"primary": False, "secondary": None}

#     def test_partial_swap_secondary_becomes_primary(self):
#         """When current secondary becomes new primary, new secondary is completely new"""
#         current_user = {
#             "Primary Email": "old_primary@test.com",
#             "Secondary Email": "old_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "old_secondary@test.com", "new_secondary@test.com")

#         assert result.change_type == "swap_partial"
#         assert result.emails_needing_verification == ["new_secondary@test.com"]
#         assert result.verification_status_updates == {"primary": False, "secondary": True}
#         assert result.subscription_updates == {"primary": None, "secondary": False}

#     def test_both_emails_completely_new(self):
#         """When both primary and secondary are brand new emails"""
#         current_user = {
#             "Primary Email": "old_primary@test.com",
#             "Secondary Email": "old_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "new_primary@test.com", "new_secondary@test.com")

#         assert result.change_type == "new_emails"
#         assert set(result.emails_needing_verification) == {"new_primary@test.com", "new_secondary@test.com"}
#         assert result.verification_status_updates == {"primary": True, "secondary": True}
#         assert result.subscription_updates == {"primary": False, "secondary": False}

#     def test_only_primary_email_new(self):
#         """When only primary email changes, secondary stays same"""
#         current_user = {
#             "Primary Email": "old_primary@test.com",
#             "Secondary Email": "keep_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "new_primary@test.com", "keep_secondary@test.com")

#         assert result.change_type == "new_emails"
#         assert result.emails_needing_verification == ["new_primary@test.com"]
#         assert result.verification_status_updates == {"primary": True, "secondary": False}
#         assert result.subscription_updates == {"primary": False, "secondary": None}

#     def test_only_secondary_email_new(self):
#         """When only secondary email changes, primary stays same"""
#         current_user = {
#             "Primary Email": "keep_primary@test.com",
#             "Secondary Email": "old_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "keep_primary@test.com", "new_secondary@test.com")

#         assert result.change_type == "new_emails"
#         assert result.emails_needing_verification == ["new_secondary@test.com"]
#         assert result.verification_status_updates == {"primary": False, "secondary": True}
#         assert result.subscription_updates == {"primary": None, "secondary": False}

#     def test_empty_current_emails(self):
#         """Handle case where current user has empty email fields"""
#         current_user = {
#             "Primary Email": "",
#             "Secondary Email": ""
#         }

#         result = analyze_email_changes(current_user, "new_primary@test.com", "new_secondary@test.com")

#         assert result.change_type == "new_emails"
#         assert set(result.emails_needing_verification) == {"new_primary@test.com", "new_secondary@test.com"}
#         assert result.verification_status_updates == {"primary": True, "secondary": True}
#         assert result.subscription_updates == {"primary": False, "secondary": False}

#     def test_empty_new_emails(self):
#         """Handle case where new emails are empty strings"""
#         current_user = {
#             "Primary Email": "old_primary@test.com",
#             "Secondary Email": "old_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "", "")

#         assert result.change_type == "new_emails"
#         assert set(result.emails_needing_verification) == {"", ""}
#         assert result.verification_status_updates == {"primary": True, "secondary": True}
#         assert result.subscription_updates == {"primary": False, "secondary": False}

#     def test_case_sensitivity(self):
#         """Email comparison should be case sensitive"""
#         current_user = {
#             "Primary Email": "user@test.com",
#             "Secondary Email": "user2@test.com"
#         }

#         result = analyze_email_changes(current_user, "USER@TEST.COM", "user2@test.com")

#         assert result.change_type == "new_emails"
#         assert result.emails_needing_verification == ["USER@TEST.COM"]
#         assert result.verification_status_updates == {"primary": True, "secondary": False}

#     def test_whitespace_handling(self):
#         """Emails with whitespace should be treated as different"""
#         current_user = {
#             "Primary Email": "user@test.com",
#             "Secondary Email": "user2@test.com"
#         }

#         result = analyze_email_changes(current_user, " user@test.com ", "user2@test.com")

#         assert result.change_type == "new_emails"
#         assert result.emails_needing_verification == [" user@test.com "]
#         assert result.verification_status_updates == {"primary": True, "secondary": False}

#     def test_return_type_structure(self):
#         """Verify the function returns proper EmailChangeDecision structure"""
#         current_user = {
#             "Primary Email": "test@test.com",
#             "Secondary Email": "test2@test.com"
#         }

#         result = analyze_email_changes(current_user, "new@test.com", "test2@test.com")

#         # Check it's the right type
#         assert isinstance(result, EmailChangeDecision)

#         # Check all required fields exist
#         assert hasattr(result, 'change_type')
#         assert hasattr(result, 'emails_needing_verification')
#         assert hasattr(result, 'verification_status_updates')
#         assert hasattr(result, 'subscription_updates')

#         # Check field types
#         assert isinstance(result.change_type, str)
#         assert isinstance(result.emails_needing_verification, list)
#         assert isinstance(result.verification_status_updates, dict)
#         assert isinstance(result.subscription_updates, dict)

#     def test_emails_needing_verification_are_new_emails(self):
#         """Any email in emails_needing_verification should not be in current user's emails"""
#         current_user = {
#             "Primary Email": "current_primary@test.com",
#             "Secondary Email": "current_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "new_primary@test.com", "current_secondary@test.com")

#         current_emails = {current_user["Primary Email"], current_user["Secondary Email"]}
#         for email in result.emails_needing_verification:
#             assert email not in current_emails

#     def test_verification_updates_consistency(self):
#         """If verification_updates[email_type] = True, then new email should need verification"""
#         current_user = {
#             "Primary Email": "old_primary@test.com",
#             "Secondary Email": "old_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "new_primary@test.com", "old_secondary@test.com")

#         if result.verification_status_updates["primary"]:
#             assert "new_primary@test.com" in result.emails_needing_verification
#         if result.verification_status_updates["secondary"]:
#             assert "old_secondary@test.com" in result.emails_needing_verification or result.change_type == "swap_partial"

#     def test_subscription_verification_relationship(self):
#         """If verification_updates[email_type] = True, then subscription_updates[email_type] = False"""
#         current_user = {
#             "Primary Email": "old_primary@test.com",
#             "Secondary Email": "old_secondary@test.com"
#         }

#         result = analyze_email_changes(current_user, "new_primary@test.com", "new_secondary@test.com")

#         for email_type in ["primary", "secondary"]:
#             if result.verification_status_updates[email_type]:
#                 assert result.subscription_updates[email_type] == False

#     @pytest.mark.parametrize("current_primary,current_secondary,new_primary,new_secondary,expected_type", [
#         # No changes
#         ("a@test.com", "b@test.com", "a@test.com", "b@test.com", "no_change"),
#         # Complete swaps
#         ("a@test.com", "b@test.com", "b@test.com", "a@test.com", "swap_complete"),
#         # Partial swaps
#         ("a@test.com", "b@test.com", "c@test.com", "a@test.com", "swap_partial"),
#         ("a@test.com", "b@test.com", "b@test.com", "c@test.com", "swap_partial"),
#         # New emails
#         ("a@test.com", "b@test.com", "c@test.com", "d@test.com", "new_emails"),
#         ("a@test.com", "b@test.com", "c@test.com", "b@test.com", "new_emails"),
#         ("a@test.com", "b@test.com", "a@test.com", "c@test.com", "new_emails"),
#     ])
#     def test_change_type_matrix(self, current_primary, current_secondary, new_primary, new_secondary, expected_type):
#         """Test various combinations to ensure correct change type detection"""
#         current_user = {
#             "Primary Email": current_primary,
#             "Secondary Email": current_secondary
#         }

#         result = analyze_email_changes(current_user, new_primary, new_secondary)
#         assert result.change_type == expected_type
