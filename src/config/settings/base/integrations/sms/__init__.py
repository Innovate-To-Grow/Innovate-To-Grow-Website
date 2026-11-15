"""
SMS policy: the deploy-level switches and bounds of the admin-editable SMS settings (Mail → SMS Settings, the
``mail.SmsConfig`` row), for Broadcast SMS, links in SMS, ticket texts and the AWS opt-out list sync.

Staff edit the policy itself on that page (footer, quiet hours, cost estimate, links, ticket texts, opt-out sync);
the values here bound what the page accepts and size the work one run does. Each comment says what it does.
"""

# Quiet hours (Mail → SMS Settings) are enforced in every deployment. The test settings switch them off so a test's
# outcome never depends on the time of day it runs; the quiet-hours tests switch them on with override_settings.
SMS_QUIET_HOURS_ENFORCED = True

SMS_POLICY = {
    # Random bytes in one SMS link token: 16 bytes are 128 bits, 22 URL-safe characters after /l/.
    "link_token_bytes": 16,
    # The longest an SMS link may stay valid, in days: bounds the campaign's and the ticket text's validity fields.
    "link_max_validity_days": 14,
    # AWS End User Messaging opted-out list read (DescribeOptedOutNumbers): numbers per page and pages per sync.
    # A list longer than page size x pages is read in part; a partial read adds opt-outs but clears none.
    "opt_out_page_size": 100,
    "opt_out_max_pages": 50,
    # Seconds to wait for each AWS call of the opt-out sync before giving up (connect and read).
    "opt_out_request_timeout_seconds": 10,
}
