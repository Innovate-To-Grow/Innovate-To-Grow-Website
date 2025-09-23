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


def split_number(number: str):
    # Handle numbers that already have "+" prefix
    if not number.startswith("+"):
        number = "+" + number
    parsed_number = phonenumbers.parse(number)
    country_code = str(parsed_number.country_code)
    country_code = "+" + country_code
    national_number = str(parsed_number.national_number)
    return country_code, national_number
