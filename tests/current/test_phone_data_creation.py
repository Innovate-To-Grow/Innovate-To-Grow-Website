"""
Unit Tests for Phone Data Integration

Tests for phone data integration with user creation and data flow.
These are pure function tests with no side effects.
"""

import pytest
from project.utils.registration_utils import (
    calculate_new_user_creation,
    calculate_phone_registration_data
)


class TestPhoneDataIntegration:
    """Test cases for phone data integration with user creation"""

    @pytest.fixture
    def base_form_data(self):
        """Base form data for user creation"""
        return {
            "first_name": "John",
            "last_name": "Doe", 
            "primary_email": "john@example.com",
            "secondary_email": "john.secondary@example.com"
        }

    @pytest.fixture
    def custom_fields(self):
        """Sample custom fields for testing"""
        return [
            {"label": "School", "field_type": "String"},
            {"label": "Interests", "field_type": "Checkbox"},
            {"label": "Department", "field_type": "Dropdown"}
        ]

    def test_user_creation_with_phone_data(self, base_form_data, custom_fields):
        """Test user creation includes phone data when provided"""
        # Create phone data
        phone_form_data = {
            "country_code": "+1",
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        phone_data = calculate_phone_registration_data(phone_form_data)
        
        # Add phone data to form data
        form_data_with_phone = base_form_data.copy()
        form_data_with_phone["phone_data"] = phone_data
        
        # Create user data
        user_data = calculate_new_user_creation(
            form_data_with_phone,
            custom_fields,
            next_order_number=1,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check that phone fields are included
        assert "Phone Number" in user_data
        assert "Phone number subscribed" in user_data
        assert "Phone number verified" in user_data
        
        # Check phone field values
        assert user_data["Phone Number"] == "+15551234567"
        assert user_data["Phone number subscribed"] == "TRUE"
        assert user_data["Phone number verified"] == "FALSE"

    def test_user_creation_without_phone_data(self, base_form_data, custom_fields):
        """Test user creation without phone data doesn't include phone fields"""
        user_data = calculate_new_user_creation(
            base_form_data,
            custom_fields,
            next_order_number=1,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check that phone fields are not included
        assert "Phone Number" not in user_data
        assert "Phone number subscribed" not in user_data
        assert "Phone number verified" not in user_data

    def test_user_creation_with_empty_phone_data(self, base_form_data, custom_fields):
        """Test user creation with empty phone data"""
        # Create empty phone data
        phone_form_data = {
            "country_code": "",
            "phone_number": "",
            "phone_subscribe": False
        }
        phone_data = calculate_phone_registration_data(phone_form_data)
        
        # Add phone data to form data
        form_data_with_phone = base_form_data.copy()
        form_data_with_phone["phone_data"] = phone_data
        
        # Create user data
        user_data = calculate_new_user_creation(
            form_data_with_phone,
            custom_fields,
            next_order_number=1,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check that phone fields are included but empty
        assert user_data["Phone Number"] == ""
        assert user_data["Phone number subscribed"] == "FALSE"
        assert user_data["Phone number verified"] == "FALSE"

    def test_phone_data_overwrites_any_existing_phone_fields(self, base_form_data, custom_fields):
        """Test that phone_data takes precedence over any existing phone fields"""
        # Form data with conflicting phone information
        form_data_with_conflicts = base_form_data.copy()
        form_data_with_conflicts["Phone Number"] = "should_be_overwritten"
        form_data_with_conflicts["Phone number subscribed"] = "should_be_overwritten"
        
        # Create correct phone data
        phone_form_data = {
            "country_code": "+1",
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        phone_data = calculate_phone_registration_data(phone_form_data)
        form_data_with_conflicts["phone_data"] = phone_data
        
        # Create user data
        user_data = calculate_new_user_creation(
            form_data_with_conflicts,
            custom_fields,
            next_order_number=1,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check that phone_data values are used, not conflicting values
        assert user_data["Phone Number"] == "+15551234567"
        assert user_data["Phone number subscribed"] == "TRUE"
        assert user_data["Phone number verified"] == "FALSE"

    def test_user_creation_preserves_all_existing_functionality(self, base_form_data, custom_fields):
        """Test that adding phone support doesn't break existing functionality"""
        # Add custom field data
        form_data_with_custom = base_form_data.copy()
        form_data_with_custom["School"] = "UC Merced"
        form_data_with_custom["Interests"] = ["Technology", "Innovation"]
        form_data_with_custom["Department"] = "Engineering"
        
        user_data = calculate_new_user_creation(
            form_data_with_custom,
            custom_fields,
            next_order_number=5,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check all existing fields are preserved
        assert user_data["Order"] == 5
        assert user_data["First Name"] == "John"
        assert user_data["Last Name"] == "Doe"
        assert user_data["Primary Email"] == "john@example.com"
        assert user_data["Secondary Email"] == "john.secondary@example.com"
        assert user_data["When Started"] == "2024-01-01 12:00 PM"
        assert user_data["Last Updated"] == "2024-01-01 12:00 PM"
        
        # Check email status fields
        assert user_data["Primary Verified"] == "TRUE"
        assert user_data["Primary Subscribed"] == "TRUE"
        assert user_data["Primary Expired"] == "FALSE"
        assert user_data["Primary Bounced"] == ""
        assert user_data["Secondary Verified"] == "FALSE"
        assert user_data["Secondary Subscribed"] == "FALSE"
        assert user_data["Secondary Expired"] == "FALSE"
        assert user_data["Secondary Bounced"] == ""
        
        # Check completion status
        assert user_data["Info Completed"] == "TRUE"
        
        # Check custom fields
        assert user_data["School"] == "UC Merced"
        assert user_data["Interests"] == "\n".join(["Technology", "Innovation"])
        assert user_data["Department"] == "Engineering"

    def test_phone_and_custom_fields_work_together(self, base_form_data, custom_fields):
        """Test that phone data and custom fields work together correctly"""
        # Create phone data
        phone_form_data = {
            "country_code": "+44",
            "phone_number": "07700900123",
            "phone_subscribe": True
        }
        phone_data = calculate_phone_registration_data(phone_form_data)
        
        # Create form data with both phone and custom fields
        comprehensive_form_data = base_form_data.copy()
        comprehensive_form_data["phone_data"] = phone_data
        comprehensive_form_data["School"] = "Oxford University"
        comprehensive_form_data["Interests"] = ["Research", "Academia"]
        comprehensive_form_data["Department"] = "Computer Science"
        
        user_data = calculate_new_user_creation(
            comprehensive_form_data,
            custom_fields,
            next_order_number=10,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check phone fields  
        assert user_data["Phone Number"] == "+4407700900123"  # UK number gets country code prepended
        assert user_data["Phone number subscribed"] == "TRUE"
        assert user_data["Phone number verified"] == "FALSE"
        
        # Check custom fields still work
        assert user_data["School"] == "Oxford University"
        assert user_data["Interests"] == "Research\nAcademia"
        assert user_data["Department"] == "Computer Science"
        
        # Check standard fields still work
        assert user_data["First Name"] == "John"
        assert user_data["Primary Email"] == "john@example.com"

    def test_checkbox_fields_with_phone_data(self, base_form_data):
        """Test that checkbox field handling works correctly with phone data"""
        custom_fields = [
            {"label": "Skills", "field_type": "Checkbox"}
        ]
        
        # Create phone data
        phone_form_data = {
            "country_code": "+1",
            "phone_number": "5551234567", 
            "phone_subscribe": False
        }
        phone_data = calculate_phone_registration_data(phone_form_data)
        
        # Form data with checkbox field
        form_data_with_checkbox = base_form_data.copy()
        form_data_with_checkbox["phone_data"] = phone_data
        form_data_with_checkbox["Skills"] = ["Python", "JavaScript", "Testing"]
        
        user_data = calculate_new_user_creation(
            form_data_with_checkbox,
            custom_fields,
            next_order_number=1,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check checkbox field is handled correctly (newline-separated)
        assert user_data["Skills"] == "Python\nJavaScript\nTesting"
        
        # Check phone data is also included
        assert user_data["Phone Number"] == "+15551234567"
        assert user_data["Phone number subscribed"] == "FALSE"

    def test_missing_custom_fields_with_phone_data(self, base_form_data, custom_fields):
        """Test handling of missing custom fields when phone data is present"""
        # Create phone data
        phone_form_data = {
            "country_code": "+1",
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        phone_data = calculate_phone_registration_data(phone_form_data)
        
        # Form data with phone but missing custom fields
        form_data_incomplete = base_form_data.copy()
        form_data_incomplete["phone_data"] = phone_data
        # Not providing School, Interests, Department
        
        user_data = calculate_new_user_creation(
            form_data_incomplete,
            custom_fields,
            next_order_number=1,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check phone data is included
        assert user_data["Phone Number"] == "+15551234567"
        assert user_data["Phone number subscribed"] == "TRUE"
        
        # Check missing custom fields are handled (should be empty or not present)
        # The function should handle missing fields gracefully
        if "School" in user_data:
            assert user_data["School"] == ""
        if "Interests" in user_data:
            assert user_data["Interests"] == ""
        if "Department" in user_data:
            assert user_data["Department"] == ""

    def test_data_type_consistency_with_phone_integration(self, base_form_data, custom_fields):
        """Test that data types remain consistent when phone data is integrated"""
        phone_form_data = {
            "country_code": "+1",
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        phone_data = calculate_phone_registration_data(phone_form_data)
        
        form_data_with_phone = base_form_data.copy()
        form_data_with_phone["phone_data"] = phone_data
        
        user_data = calculate_new_user_creation(
            form_data_with_phone,
            custom_fields,
            next_order_number=1,
            current_timestamp="2024-01-01 12:00 PM"
        )
        
        # Check that all values are strings (as expected for worksheet storage)
        for key, value in user_data.items():
            if key == "Order":
                assert isinstance(value, int), f"{key} should be int, got {type(value)}"
            else:
                assert isinstance(value, str), f"{key} should be string, got {type(value)}: {value}"

    def test_phone_data_structure_compatibility(self):
        """Test that phone data structure is compatible with user data structure"""
        phone_form_data = {
            "country_code": "+1", 
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        
        phone_data = calculate_phone_registration_data(phone_form_data)
        
        # Check that phone data structure can be merged into user data
        expected_keys = {"Phone Number", "Phone number subscribed", "Phone number verified"}
        assert set(phone_data.keys()) == expected_keys
        
        # Check that all values are strings (compatible with worksheet storage)
        for key, value in phone_data.items():
            assert isinstance(value, str), f"Phone data {key} should be string, got {type(value)}"
        
        # Check specific string values
        assert phone_data["Phone number subscribed"] in ["TRUE", "FALSE"]
        assert phone_data["Phone number verified"] == "FALSE"
