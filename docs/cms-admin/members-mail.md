# Members and Mail Tooling

## Member management

- Members can be created, invited, or imported from Excel.
- Contact emails and phones are managed independently and track verification and subscription state.
- Group assignment and invitation handling remain inside the auth admin workflow.

## Mail tooling

- Gmail API accounts and SES accounts are configured in Django admin.
- Compose flows write to audit models and sanitize outbound HTML.
- Email logs show delivery attempts and provider metadata for troubleshooting.

## Practical checks

- Verify Gmail or SES configuration before running large email sends.
- Confirm imported members have usernames, verified primary email state, and expected subscription flags.
- Re-test auto-login links after changing auth or ticket mail templates.
