CHANGE_READONLY_FIELDS = (
    "member",
    "event",
    "ticket_code",
    "attendee_first_name",
    "attendee_last_name",
    "attendee_email",
    "attendee_secondary_email",
    "attendee_phone",
    "phone_verified",
    "attendee_organization",
    "question_answers",
    "send_ticket_email_action",
    "ticket_email_sent_at",
    "ticket_email_error",
    "created_at",
    "updated_at",
)

ADD_READONLY_FIELDS = (
    "ticket_code",
    "ticket_email_sent_at",
    "ticket_email_error",
    "created_at",
    "updated_at",
)

CHANGE_FIELDSETS = (
    (
        "Attendee",
        {
            "description": (
                "Read-only attendee snapshot for this event registration. "
                "Changing the ticket below does not update the member account profile or contact records."
            ),
            "fields": (
                "attendee_first_name",
                "attendee_last_name",
                "attendee_email",
                "attendee_secondary_email",
                "attendee_phone",
                "phone_verified",
                "attendee_organization",
            ),
        },
    ),
    (
        "Ticket",
        {
            "description": (
                "Only the ticket can be changed. Event, member, and ticket code are "
                "locked; ticket choices are limited to this event."
            ),
            "fields": ("event", "ticket", "ticket_code", "member"),
        },
    ),
    (
        "Questions & Answers",
        {
            "classes": ("collapse",),
            "description": "Read-only JSON list of registration question answers.",
            "fields": ("question_answers",),
        },
    ),
    (
        "Options",
        {
            "description": "Click to save the current ticket selection and send a new confirmation email immediately.",
            "fields": ("send_ticket_email_action",),
        },
    ),
    (
        "Email Status",
        {
            "classes": ("collapse",),
            "description": "Read-only ticket email delivery history.",
            "fields": ("ticket_email_sent_at", "ticket_email_error"),
        },
    ),
    (
        "System",
        {
            "classes": ("collapse",),
            "description": "Read-only audit timestamps.",
            "fields": ("created_at", "updated_at"),
        },
    ),
)

ADD_FIELDSETS = (
    (
        "Registration",
        {
            "fields": ("member", "event", "ticket"),
        },
    ),
    (
        "Attendee overrides",
        {
            "description": "Leave blank to auto-fill from the member's profile.",
            "classes": ("collapse",),
            "fields": (
                "attendee_first_name",
                "attendee_last_name",
                "attendee_email",
                "attendee_secondary_email",
                "attendee_phone",
                "attendee_organization",
            ),
        },
    ),
    (
        "Options",
        {
            "fields": ("send_ticket_email",),
        },
    ),
)

EXPORT_FIELDS = (
    ("id", "Registration ID"),
    ("ticket_code", "Ticket Code"),
    ("event_name", "Event Name"),
    ("event_slug", "Event Slug"),
    ("event_date", "Event Date"),
    ("ticket_name", "Ticket"),
    ("attendee_first_name", "Attendee First Name"),
    ("attendee_last_name", "Attendee Last Name"),
    ("attendee_name", "Attendee Full Name"),
    ("attendee_email", "Attendee Email"),
    ("attendee_secondary_email", "Attendee Secondary Email"),
    ("attendee_phone", "Attendee Phone"),
    ("phone_verified", "Attendee Phone Verified"),
    ("attendee_organization", "Attendee Organization"),
    ("question_answers", "Question Answers"),
    ("created_at", "Registered At"),
    ("updated_at", "Updated At"),
    ("ticket_email_sent_at", "Ticket Email Sent At"),
    ("ticket_email_error", "Ticket Email Error"),
    ("member_id", "Member ID"),
    ("member_full_name", "Member Full Name"),
    ("member_first_name", "Member First Name"),
    ("member_middle_name", "Member Middle Name"),
    ("member_last_name", "Member Last Name"),
    ("member_title", "Member Title"),
    ("member_organization", "Member Organization"),
    ("member_primary_email", "Member Primary Email"),
    ("member_secondary_emails", "Member Secondary Emails"),
    ("member_other_emails", "Member Other Emails"),
    ("member_phone_numbers", "Member Phone Numbers"),
)
