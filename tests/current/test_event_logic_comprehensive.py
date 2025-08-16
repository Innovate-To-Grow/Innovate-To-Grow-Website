# import pytest
# from project.utils.event_utils import make_sure


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
