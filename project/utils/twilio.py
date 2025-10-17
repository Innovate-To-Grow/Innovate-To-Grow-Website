import phonenumbers
from twilio.rest import Client
from config.default import Config


account_sid = Config.TWILIO_ACCOUNT_SID
auth_token = Config.TWILIO_AUTH_TOKEN
twilio_num = Config.TWILIO_NUMBER
verify_sid = Config.VERIFY_SID
client = Client(account_sid, auth_token)


def send_message(body: str, to: str, client: Client):
    message = client.messages.create(
        body=body,
        from_=twilio_num,
        to=to
    )

def start_verification_process(client: Client, phone_number: str, verify_sid: str):
    verification = client.verify.v2.services(verify_sid) \
        .verifications \
        .create(to=phone_number, channel="sms")
    return verification.status

def check_verification(client: Client, phone_number: str, verify_sid: str, otp_code: str):
    verification_check = client.verify.v2.services(verify_sid) \
    .verification_checks \
    .create(to=phone_number, code=otp_code)
    return verification_check.status


def validate_phone_number_exists(phone_number: str) -> dict:
    """
    Uses Twilio Lookup API to validate if a phone number actually exists and can receive SMS.
    
    Args:
        phone_number: Full international phone number (e.g., "+15551234567")
    
    Returns:
        Dictionary with validation results:
        {
            "valid": bool,
            "phone_number": str,  # E.164 formatted number
            "carrier": dict,       # Carrier info (if requested)
            "error": str or None
        }
    """
    # Basic sanity check - ensure phone number is provided
    if not phone_number or phone_number.strip() == "":
        return {
            "valid": False,
            "phone_number": phone_number,
            "national_format": None,
            "country_code": None,
            "error": "Phone number is required"
        }
    
    # Parse the phone number to extract national number portion
    # This allows us to check patterns independently of the country code
    try:
        # Ensure the number has a + prefix for parsing
        number_to_parse = phone_number if phone_number.startswith("+") else "+" + phone_number
        parsed = phonenumbers.parse(number_to_parse, None)
        national_number = str(parsed.national_number)
        country_code = parsed.country_code
    except Exception as e:
        # If parsing fails, fall back to basic digit extraction
        national_number = phone_number.replace("+", "").replace(" ", "").replace("-", "")
        # Remove the first 1-3 digits (country code) if the number is long enough
        if len(national_number) > 10:
            national_number = national_number[-10:]  # Take last 10 digits for US numbers
        country_code = None
    
    # Validate US phone numbers have exactly 10 digits
    if country_code == 1:  # US/Canada country code
        if len(national_number) != 10:
            return {
                "valid": False,
                "phone_number": phone_number,
                "national_format": None,
                "country_code": None,
                "error": f"US phone numbers must be exactly 10 digits (got {len(national_number)} digits)"
            }
    
    # Pattern validation on the NATIONAL NUMBER only (excluding country code)
    # This prevents patterns like +18888888888 from slipping through
    
    # Check for all same digit (0000000000, 1111111111, 8888888888, etc.)
    if len(national_number) >= 10 and len(set(national_number)) == 1:
        return {
            "valid": False,
            "phone_number": phone_number,
            "national_format": None,
            "country_code": None,
            "error": "Invalid phone number pattern - appears to be a test number"
        }
    
    # Check for sequential patterns (1234567890, 0123456789, 9876543210)
    if national_number in ["1234567890", "0123456789", "9876543210"]:
        return {
            "valid": False,
            "phone_number": phone_number,
            "national_format": None,
            "country_code": None,
            "error": "Invalid phone number pattern - appears to be a test number"
        }
    
    # Check for alternating/repetitive patterns (too few unique digits)
    # This catches patterns like 1212121212, 1231231231, etc.
    if len(national_number) >= 10 and len(set(national_number)) <= 2:
        return {
            "valid": False,
            "phone_number": phone_number,
            "national_format": None,
            "country_code": None,
            "error": "Invalid phone number pattern - appears to be a test number"
        }
    
    try:
        # Twilio Lookup API validates the number exists and returns carrier info
        # Using line_type_intelligence to check if number can receive SMS
        phone_info = client.lookups.v2.phone_numbers(phone_number).fetch(
            fields='line_type_intelligence'
        )
        
        # Check if the phone number is valid and can receive SMS
        valid = phone_info.valid
        
        # Additional validation: check if line type intelligence indicates it's a valid mobile/landline
        # that can receive SMS
        error_message = None
        if not valid:
            error_message = "Phone number is not valid or cannot be reached"
        
        # Check line type if available
        if hasattr(phone_info, 'line_type_intelligence') and phone_info.line_type_intelligence:
            line_info = phone_info.line_type_intelligence
            # If the number type indicates it cannot receive SMS, mark as invalid
            if hasattr(line_info, 'type') and line_info.type in ['voip', 'nonFixedVoip']:
                # VOIP numbers might not receive SMS reliably, but we'll allow them
                pass
            if hasattr(line_info, 'error_code') and line_info.error_code:
                valid = False
                error_message = f"Phone validation error: {line_info.error_code}"
        
        return {
            "valid": valid,
            "phone_number": phone_info.phone_number,
            "national_format": phone_info.national_format,
            "country_code": phone_info.country_code,
            "error": error_message
        }
    except Exception as e:
        error_message = str(e)
        
        # Parse common Twilio errors
        if "20404" in error_message:
            error_message = "Phone number not found or invalid"
        elif "21211" in error_message:
            error_message = "Invalid phone number format"
        elif "21608" in error_message:
            error_message = "This phone number cannot receive SMS messages"
        elif "60200" in error_message:
            error_message = "Invalid phone number - cannot create verification"
        
        return {
            "valid": False,
            "phone_number": phone_number,
            "national_format": None,
            "country_code": None,
            "error": error_message
        }


def split_number(number: str):
    # Handle numbers that already have "+" prefix
    if not number.startswith("+"):
        number = "+" + number
    parsed_number = phonenumbers.parse(number)
    country_code = str(parsed_number.country_code)
    country_code = "+" + country_code
    national_number = str(parsed_number.national_number)
    return country_code, national_number
