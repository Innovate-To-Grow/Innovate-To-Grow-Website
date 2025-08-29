"""
Unit Tests for Phone Number Conflict Detection

Tests for analyze_phone_number_conflicts() function.
These are pure function tests with no side effects.
"""

import pytest
from project.utils.registration_utils import analyze_phone_number_conflicts


class TestAnalyzePhoneNumberConflicts:
    """Test cases for analyze_phone_number_conflicts() function"""

    @pytest.fixture
    def sample_user_records(self):
        """Sample user records for testing"""
        return [
            {
                "Row": 1,
                "First Name": "John",
                "Last Name": "Doe", 
                "Phone Number": "+15551234567",
                "Primary Email": "john@example.com"
            },
            {
                "Row": 2,
                "First Name": "Jane",
                "Last Name": "Smith",
                "Phone Number": "+447700900123", 
                "Primary Email": "jane@example.com"
            },
            {
                "Row": 3,
                "First Name": "Bob",
                "Last Name": "Wilson",
                "Phone Number": "",  # No phone number
                "Primary Email": "bob@example.com"
            },
            {
                "Row": 4,
                "First Name": "Alice",
                "Last Name": "Johnson",
                "Phone Number": "+12345",  # Short phone number
                "Primary Email": "alice@example.com"
            }
        ]

    def test_no_phone_number_provided_no_conflict(self, sample_user_records):
        """Test that empty phone number results in no conflict"""
        result = analyze_phone_number_conflicts(sample_user_records, "")
        
        assert result["has_conflict"] is False
        assert result["conflicting_user"] is None
        assert result["can_proceed"] is True
        assert result["conflict_details"] is None

    def test_none_phone_number_no_conflict(self, sample_user_records):
        """Test that None phone number results in no conflict"""
        result = analyze_phone_number_conflicts(sample_user_records, None)
        
        assert result["has_conflict"] is False
        assert result["conflicting_user"] is None
        assert result["can_proceed"] is True
        assert result["conflict_details"] is None

    def test_whitespace_only_phone_no_conflict(self, sample_user_records):
        """Test that whitespace-only phone number results in no conflict"""
        whitespace_phones = ["   ", "\t\t", "\n\n", " \t\n "]
        
        for phone in whitespace_phones:
            result = analyze_phone_number_conflicts(sample_user_records, phone)
            
            assert result["has_conflict"] is False
            assert result["conflicting_user"] is None
            assert result["can_proceed"] is True
            assert result["conflict_details"] is None

    def test_unique_phone_number_no_conflict(self, sample_user_records):
        """Test that unique phone number results in no conflict"""
        unique_phones = [
            "+15559999999",
            "+447700999999", 
            "+81901234567",
            "+33123456789"
        ]
        
        for phone in unique_phones:
            result = analyze_phone_number_conflicts(sample_user_records, phone)
            
            assert result["has_conflict"] is False
            assert result["conflicting_user"] is None
            assert result["can_proceed"] is True
            assert result["conflict_details"] is None

    def test_existing_phone_number_has_conflict(self, sample_user_records):
        """Test that existing phone number results in conflict"""
        result = analyze_phone_number_conflicts(sample_user_records, "+15551234567")
        
        assert result["has_conflict"] is True
        assert result["conflicting_user"] is not None
        assert result["can_proceed"] is False
        assert result["conflict_details"] is not None
        
        # Check conflict details
        conflict = result["conflict_details"]
        assert conflict["existing_user_row"] == 1
        assert conflict["existing_user_name"] == "John Doe"
        assert conflict["phone_number"] == "+15551234567"
        assert conflict["existing_user"]["First Name"] == "John"

    def test_multiple_existing_phones_returns_first_match(self):
        """Test that when multiple users have same phone, first match is returned"""
        # Create records with duplicate phone numbers
        records_with_duplicates = [
            {
                "Row": 1,
                "First Name": "First", 
                "Last Name": "User",
                "Phone Number": "+15551234567"
            },
            {
                "Row": 2,
                "First Name": "Second",
                "Last Name": "User", 
                "Phone Number": "+15551234567"  # Same phone
            }
        ]
        
        result = analyze_phone_number_conflicts(records_with_duplicates, "+15551234567")
        
        assert result["has_conflict"] is True
        assert result["conflicting_user"]["Row"] == 1  # First match
        assert result["conflict_details"]["existing_user_name"] == "First User"

    def test_phone_number_whitespace_trimming(self, sample_user_records):
        """Test that phone numbers are properly trimmed for comparison"""
        # Test phone with extra whitespace should match existing record
        result = analyze_phone_number_conflicts(sample_user_records, "  +15551234567  ")
        
        assert result["has_conflict"] is True
        assert result["conflicting_user"]["First Name"] == "John"
        assert result["conflict_details"]["phone_number"] == "+15551234567"  # Cleaned phone number

    def test_case_sensitivity_phone_numbers(self, sample_user_records):
        """Test that phone number matching is case sensitive (though phones shouldn't have letters)"""
        # This is more of a validation that we do exact matching
        result = analyze_phone_number_conflicts(sample_user_records, "+15551234567")
        assert result["has_conflict"] is True
        
        # Different case shouldn't exist in real data, but test exact matching
        result = analyze_phone_number_conflicts(sample_user_records, "+15551234568")
        assert result["has_conflict"] is False

    def test_empty_user_records_no_conflict(self):
        """Test that empty user records result in no conflict"""
        result = analyze_phone_number_conflicts([], "+15551234567")
        
        assert result["has_conflict"] is False
        assert result["conflicting_user"] is None
        assert result["can_proceed"] is True
        assert result["conflict_details"] is None

    def test_records_missing_phone_number_field(self):
        """Test graceful handling of records missing Phone Number field"""
        records_missing_phone = [
            {
                "Row": 1,
                "First Name": "John",
                "Last Name": "Doe"
                # Missing "Phone Number" field
            }
        ]
        
        result = analyze_phone_number_conflicts(records_missing_phone, "+15551234567")
        
        assert result["has_conflict"] is False
        assert result["conflicting_user"] is None
        assert result["can_proceed"] is True

    def test_records_with_none_phone_values(self):
        """Test handling of records where Phone Number field is None"""
        records_with_none_phone = [
            {
                "Row": 1,
                "First Name": "John",
                "Last Name": "Doe",
                "Phone Number": None
            }
        ]
        
        result = analyze_phone_number_conflicts(records_with_none_phone, "+15551234567")
        
        assert result["has_conflict"] is False
        assert result["conflicting_user"] is None
        assert result["can_proceed"] is True

    def test_conflict_details_structure(self, sample_user_records):
        """Test that conflict details have the correct structure"""
        result = analyze_phone_number_conflicts(sample_user_records, "+15551234567")
        
        assert result["has_conflict"] is True
        conflict = result["conflict_details"]
        
        # Check all required fields are present
        required_fields = [
            "existing_user_row",
            "existing_user_name", 
            "phone_number",
            "existing_user"
        ]
        
        for field in required_fields:
            assert field in conflict
        
        # Check field types and values
        assert isinstance(conflict["existing_user_row"], int)
        assert isinstance(conflict["existing_user_name"], str)
        assert isinstance(conflict["phone_number"], str)
        assert isinstance(conflict["existing_user"], dict)
        
        # Check specific values
        assert conflict["existing_user_row"] == 1
        assert conflict["existing_user_name"] == "John Doe"
        assert conflict["phone_number"] == "+15551234567"

    def test_short_phone_number_conflict(self, sample_user_records):
        """Test conflict detection with short phone numbers"""
        result = analyze_phone_number_conflicts(sample_user_records, "+12345")
        
        assert result["has_conflict"] is True
        assert result["conflicting_user"]["First Name"] == "Alice"
        assert result["conflict_details"]["phone_number"] == "+12345"

    def test_return_structure_consistency(self, sample_user_records):
        """Test that return structure is consistent for all scenarios"""
        test_cases = [
            ("", False),                    # Empty phone
            ("+15559999999", False),       # Unique phone
            ("+15551234567", True),        # Conflicting phone
        ]
        
        required_keys = ["has_conflict", "conflicting_user", "can_proceed", "conflict_details"]
        
        for phone, should_conflict in test_cases:
            result = analyze_phone_number_conflicts(sample_user_records, phone)
            
            # Check all required keys are present
            for key in required_keys:
                assert key in result
            
            # Check logical consistency
            assert result["has_conflict"] == should_conflict
            assert result["can_proceed"] == (not should_conflict)
            
            if should_conflict:
                assert result["conflicting_user"] is not None
                assert result["conflict_details"] is not None
            else:
                assert result["conflicting_user"] is None
                assert result["conflict_details"] is None

    def test_phone_numbers_must_be_unique_business_rule(self, sample_user_records):
        """Test that the business rule 'phone numbers must be unique' is enforced"""
        # This test verifies that ANY existing phone number blocks registration
        existing_phones = ["+15551234567", "+447700900123", "+12345"]
        
        for phone in existing_phones:
            result = analyze_phone_number_conflicts(sample_user_records, phone)
            
            assert result["has_conflict"] is True
            assert result["can_proceed"] is False  # Always block on phone conflicts
            
    def test_malformed_user_records_handling(self):
        """Test handling of malformed user records"""
        malformed_records = [
            {},  # Empty record
            {"Row": "not_a_number"},  # Invalid row
            {"First Name": "John"},   # Missing required fields
            {"Phone Number": "+15551234567"},  # Missing name fields
        ]
        
        # Should not crash, should handle gracefully
        result = analyze_phone_number_conflicts(malformed_records, "+15551234567")
        
        # Even with malformed records, if phone matches, should detect conflict
        assert result["has_conflict"] is True
        assert result["can_proceed"] is False
