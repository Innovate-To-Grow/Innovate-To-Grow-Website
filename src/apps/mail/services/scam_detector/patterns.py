import re

MEDIUM_THRESHOLD = 3
HIGH_THRESHOLD = 7

URGENCY_SUBJECT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\burgent\b",
        r"\bact now\b",
        r"\bimmediate(ly)?\b",
        r"\bsuspend(ed)?\b",
        r"\bverif(y|ication)\b",
        r"\bconfirm your\b",
        r"\baccount.{0,15}(clos|lock|restrict|limit)",
        r"\bprize\b",
        r"\bwinner\b",
        r"\bwon\b",
        r"\blotter(y|ies)\b",
        r"\binheritance\b",
        r"\bunclaimed\b",
        r"\bfinal (notice|warning)\b",
        r"\baction required\b",
        r"\bexpir(e[sd]?|ing|ation)\b",
    ]
]

BODY_URGENCY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bclick here\b",
        r"\bact (now|immediately)\b",
        r"\blimited time\b",
        r"\bdo not ignore\b",
        r"\bfailure to (respond|comply|verify)",
        r"\byour account (has been|will be|is)\s",
        r"\bwithin \d+ (hour|day|business day)",
        r"\bimmediately\b",
    ]
]

PERSONAL_INFO_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(social security|ssn)\b",
        r"\bpassword\b",
        r"\bcredit card\b",
        r"\bbank account\b",
        r"\bpin (number|code)\b",
        r"\bdate of birth\b",
        r"\btax(payer)? id\b",
        r"\brouting number\b",
        r"\baccount number\b",
        r"\bwire transfer\b",
    ]
]

GENERIC_GREETING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bdear (customer|user|member|account holder|valued|sir|madam|client)\b",
        r"\bdear friend\b",
        r"\bhello dear\b",
    ]
]

MONEY_PATTERN = re.compile(r"(?:\$|USD|EUR|GBP|£|€)\s?[\d,]{4,}", re.IGNORECASE)

FREEMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "aol.com",
        "mail.com",
        "protonmail.com",
        "yandex.com",
        "zoho.com",
        "icloud.com",
        "gmx.com",
        "live.com",
    }
)

BRAND_KEYWORDS_IN_NAME = re.compile(
    r"\b(amazon|paypal|apple|microsoft|google|netflix|bank|wells fargo"
    r"|chase|citibank|hsbc|irs|fedex|ups|dhl|usps)\b",
    re.IGNORECASE,
)

URL_SHORTENERS = frozenset(
    {
        "bit.ly",
        "tinyurl.com",
        "goo.gl",
        "t.co",
        "ow.ly",
        "is.gd",
        "buff.ly",
        "rebrand.ly",
        "shorturl.at",
        "tiny.cc",
        "cutt.ly",
    }
)

IP_URL_PATTERN = re.compile(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
