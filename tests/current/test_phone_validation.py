"""
Unit Tests for Phone Number Validation Logic

Tests for phone number validation, formatting, and data creation functions.
These are pure function tests with no side effects.
"""

import pytest
from project.utils.registration_utils import (
    validate_and_format_phone_number,
    calculate_phone_registration_data
)


class TestValidateAndFormatPhoneNumber:
    """Test cases for validate_and_format_phone_number() function"""

    def test_empty_phone_number_is_valid(self):
        """Test that empty phone number is considered valid"""
        result = validate_and_format_phone_number("", "")
        
        assert result["is_valid"] is True
        assert result["formatted_number"] == ""
        assert result["error_message"] is None

    def test_empty_phone_with_country_code_is_valid(self):
        """Test that empty phone with country code returns empty result"""
        result = validate_and_format_phone_number("+1", "")
        
        assert result["is_valid"] is True
        assert result["formatted_number"] == ""
        assert result["error_message"] is None

    def test_phone_without_country_code_is_invalid(self):
        """Test that phone number without country code is invalid"""
        result = validate_and_format_phone_number("", "5551234567")
        
        assert result["is_valid"] is False
        assert result["formatted_number"] == ""
        assert result["error_message"] == "Country code is required when phone number is provided"

    def test_valid_us_phone_number_formatting(self):
        """Test valid US phone number gets formatted correctly"""
        test_cases = [
            ("5551234567", "+15551234567"),
            ("555-123-4567", "+15551234567"),
            ("(555) 123-4567", "+15551234567"),
            ("555.123.4567", "+15551234567"),
            ("555 123 4567", "+15551234567"),
        ]
        
        for input_phone, expected_output in test_cases:
            result = validate_and_format_phone_number("+1", input_phone)
            
            assert result["is_valid"] is True
            assert result["formatted_number"] == expected_output
            assert result["error_message"] is None

    def test_valid_international_phone_numbers(self):
        """Test various international phone number formats"""
        test_cases = [
            ("+44", "07700900123", "+4407700900123"),  # UK number gets country code prepended
            ("+81", "90-1234-5678", "+819012345678"),  # All digits extracted: 901234567 8
            ("+49", "030 12345678", "+4903012345678"),
            ("+33", "01.23.45.67.89", "+330123456789"),  # All digits extracted
        ]
        
        for country_code, phone, expected in test_cases:
            result = validate_and_format_phone_number(country_code, phone)
            
            assert result["is_valid"] is True
            assert result["formatted_number"] == expected
            assert result["error_message"] is None

    def test_phone_with_letters_gets_digits_extracted(self):
        """Test that phone numbers containing letters get digits extracted"""
        test_cases = [
            ("555-CALL-NOW", "+1555"),  # Only digits extracted: 555
            ("abc123def", "+1123"),     # Only digits extracted: 123
            ("555abc4567", "+15554567"), # Only digits extracted: 5554567
        ]
        
        for input_phone, expected_output in test_cases:
            result = validate_and_format_phone_number("+1", input_phone)
            
            assert result["is_valid"] is True
            assert result["formatted_number"] == expected_output
            assert result["error_message"] is None

    def test_phone_with_no_digits_is_invalid(self):
        """Test that phone numbers with no digits are invalid"""
        invalid_phones = [
            "phone-number",  # No digits
            "CALL-NOW",      # No digits
            "abc-def",       # No digits
        ]
        
        for invalid_phone in invalid_phones:
            result = validate_and_format_phone_number("+1", invalid_phone)
            
            assert result["is_valid"] is False
            assert result["formatted_number"] == ""
            assert result["error_message"] == "Invalid phone number format"

    def test_phone_with_only_special_characters_is_invalid(self):
        """Test that phone numbers with only special characters are invalid"""
        invalid_phones = [
            "---",
            "().",
            "+-*/",
        ]
        
        for invalid_phone in invalid_phones:
            result = validate_and_format_phone_number("+1", invalid_phone)
            
            assert result["is_valid"] is False
            assert result["formatted_number"] == ""
            assert result["error_message"] == "Invalid phone number format"

    def test_whitespace_handling(self):
        """Test that whitespace is properly trimmed from inputs"""
        test_cases = [
            ("  +1  ", "  555 123 4567  ", "+15551234567"),
            ("\t+44\t", "\n07700900123\n", "+4407700900123"),  # UK number gets country code prepended
            ("   +1   ", "   ", ""),  # Whitespace-only phone becomes empty
        ]
        
        for country_code, phone, expected in test_cases:
            result = validate_and_format_phone_number(country_code, phone)
            
            assert result["is_valid"] is True
            assert result["formatted_number"] == expected

    def test_none_values_handling(self):
        """Test graceful handling of None values"""
        # None phone number should be treated as empty
        result = validate_and_format_phone_number("+1", None)
        assert result["is_valid"] is True
        assert result["formatted_number"] == ""
        
        # None country code should be treated as empty
        result = validate_and_format_phone_number(None, "5551234567")
        assert result["is_valid"] is False
        assert result["error_message"] == "Country code is required when phone number is provided"

    def test_short_phone_numbers_are_valid(self):
        """Test that short phone numbers are allowed"""
        result = validate_and_format_phone_number("+1", "12345")
        
        assert result["is_valid"] is True
        assert result["formatted_number"] == "+112345"
        assert result["error_message"] is None

    def test_very_long_phone_numbers_are_valid(self):
        """Test that very long phone numbers are allowed"""
        long_phone = "1234567890123456789"
        result = validate_and_format_phone_number("+1", long_phone)
        
        assert result["is_valid"] is True
        assert result["formatted_number"] == f"+1{long_phone}"
        assert result["error_message"] is None


class TestCalculatePhoneRegistrationData:
    """Test cases for calculate_phone_registration_data() function"""

    def test_valid_phone_data_with_subscription(self):
        """Test phone data creation with subscription enabled"""
        form_data = {
            "country_code": "+1",
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        
        result = calculate_phone_registration_data(form_data)
        
        expected = {
            "Phone Number": "+15551234567",
            "Phone number subscribed": "TRUE",
            "Phone number verified": "FALSE"
        }
        
        assert result == expected

    def test_valid_phone_data_without_subscription(self):
        """Test phone data creation with subscription disabled"""
        form_data = {
            "country_code": "+1", 
            "phone_number": "5551234567",
            "phone_subscribe": False
        }
        
        result = calculate_phone_registration_data(form_data)
        
        expected = {
            "Phone Number": "+15551234567",
            "Phone number subscribed": "FALSE",
            "Phone number verified": "FALSE"
        }
        
        assert result == expected

    def test_empty_phone_data(self):
        """Test phone data creation with no phone number"""
        form_data = {
            "country_code": "",
            "phone_number": "",
            "phone_subscribe": True
        }
        
        result = calculate_phone_registration_data(form_data)
        
        expected = {
            "Phone Number": "",
            "Phone number subscribed": "TRUE",
            "Phone number verified": "FALSE"
        }
        
        assert result == expected

    def test_phone_subscribe_boolean_conversion(self):
        """Test that phone_subscribe is properly converted to string"""
        test_cases = [
            (True, "TRUE"),
            (False, "FALSE"),
            (1, "TRUE"),  # Truthy values
            (0, "FALSE"), # Falsy values
            ("true", "TRUE"),  # String values
            ("", "FALSE"),
            (None, "FALSE"),
        ]
        
        for subscribe_value, expected_string in test_cases:
            form_data = {
                "country_code": "+1",
                "phone_number": "5551234567", 
                "phone_subscribe": subscribe_value
            }
            
            result = calculate_phone_registration_data(form_data)
            assert result["Phone number subscribed"] == expected_string

    def test_missing_form_fields_use_defaults(self):
        """Test that missing form fields use appropriate defaults"""
        # Missing phone_subscribe should default to False
        form_data = {
            "country_code": "+1",
            "phone_number": "5551234567"
            # phone_subscribe is missing
        }
        
        result = calculate_phone_registration_data(form_data)
        assert result["Phone number subscribed"] == "FALSE"
        
        # Missing country_code and phone_number
        form_data = {
            "phone_subscribe": True
        }
        
        result = calculate_phone_registration_data(form_data)
        assert result["Phone Number"] == ""

    def test_phone_verified_always_false_initially(self):
        """Test that phone_verified is always FALSE for new registrations"""
        form_data = {
            "country_code": "+1",
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        
        result = calculate_phone_registration_data(form_data)
        assert result["Phone number verified"] == "FALSE"

    def test_invalid_phone_raises_value_error(self):
        """Test that invalid phone validation raises ValueError"""
        form_data = {
            "country_code": "",  # Missing country code
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        
        with pytest.raises(ValueError) as exc_info:
            calculate_phone_registration_data(form_data)
        
        assert "Phone validation failed" in str(exc_info.value)
        assert "Country code is required" in str(exc_info.value)

    def test_field_names_are_exact(self):
        """Test that field names match exactly what's expected in the worksheet"""
        form_data = {
            "country_code": "+1",
            "phone_number": "5551234567",
            "phone_subscribe": True
        }
        
        result = calculate_phone_registration_data(form_data)
        
        # These exact field names must match the worksheet columns
        expected_keys = {
            "Phone Number",
            "Phone number subscribed", 
            "Phone number verified"
        }
        
        assert set(result.keys()) == expected_keys
