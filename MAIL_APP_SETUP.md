# Mail App Setup Guide

The `mail` app provides two separate admin mail tools:

- Gmail inbox/outbox/compose/reply/forward via the Gmail API and Domain-Wide Delegation
- A dedicated SES compose flow for sending new outbound mail as `i2g@g.ucmerced.edu`

## Prerequisites

- Python packages: `google-api-python-client`, `google-auth`, `bleach` (already in `requirements.txt`)
- A Google Workspace domain with admin access

## 1. Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the **Gmail API**: APIs & Services → Library → Search "Gmail API" → Enable
4. Create a **Service Account**:
   - APIs & Services → Credentials → Create Credentials → Service Account
   - Name it (e.g., "ITG Gmail Service Account")
   - Grant no additional roles (permissions come from delegation)
   - Click the service account → Keys → Add Key → Create new key → JSON
   - **Download the JSON key file** — you'll paste its contents into Django Admin

## 2. Domain-Wide Delegation

1. In Google Cloud Console, go to your service account → Details
2. Copy the **Client ID** (numeric)
3. Go to [Google Workspace Admin Console](https://admin.google.com/)
4. Security → Access and data control → API controls → **Manage Domain Wide Delegation**
5. Click **Add new** and enter:
   - **Client ID**: The numeric ID from step 2
   - **OAuth Scopes**: `https://www.googleapis.com/auth/gmail.modify`
6. Click **Authorize**

## 3. Django Setup

```bash
# Install dependencies
pip install -r src/requirements.txt

# Run migrations
cd src
python manage.py migrate --settings=core.settings.dev
```

## 4. Add Gmail Account in Admin

1. Start the dev server: `python manage.py runserver`
2. Go to `/admin/mail/googleaccount/`
3. Click **Add Gmail API Account**
4. Fill in:
   - **Email**: The Gmail address to access (e.g., `i2g@g.ucmerced.edu`)
   - **Display name**: Sender name (e.g., "Innovate to Grow")
   - **Service account JSON**: Paste the entire contents of the downloaded JSON key file
   - **Is active**: Check this box
5. Save

## 5. Test Connection

### Via Management Command

```bash
python manage.py test_gmail_connection --settings=core.settings.dev
```

### Via Admin Action

1. Go to `/admin/mail/googleaccount/`
2. Select the account → Actions → "Test Gmail API connection" → Go

## 6. Usage

### Inbox
Navigate to `/admin/mail/googleaccount/inbox/` or click **Inbox** in the sidebar.
- Search emails using the search bar (uses Gmail search syntax)
- Click a message to read it (auto-marks as read)
- Paginate through results

### Compose
Navigate to `/admin/mail/googleaccount/compose/` or click **Compose** in the sidebar.
- Fill in To, CC, BCC, Subject, and Body (HTML supported)
- Attach files if needed
- Click **Send**

### Reply / Forward
From any message detail view:
- Click **Reply** to reply (pre-fills To, Subject with "Re:", and quotes the original)
- Click **Forward** to forward (pre-fills Subject with "Fwd:" and includes the original)

### Sent Mail
Navigate to `/admin/mail/googleaccount/sent/` or click **Sent Mail** in the sidebar.

### Email Logs
All operations are logged. View at `/admin/mail/emaillog/` or **Email Logs** in the sidebar.

## Troubleshooting

- **"No active Gmail API account"**: Add a GoogleAccount in admin and make sure `is_active` is checked
- **"Failed to build Gmail service"**: Verify the service account JSON is valid and complete
- **"403 Forbidden"**: Domain-Wide Delegation is not configured, or the wrong scope was authorized
- **"401 Unauthorized"**: The service account key may be expired or revoked

## SES Admin Sender

The SES sender is a separate admin entry intended for the new ECS-deployed I2G system.

### Required runtime environment

- `SES_AWS_ACCESS_KEY_ID`
- `SES_AWS_SECRET_ACCESS_KEY`
- `SES_AWS_REGION`
- `SES_FROM_EMAIL`
- `SES_FROM_NAME`

### Admin usage

1. Go to `/admin/mail/sesaccount/`
2. Open **Compose SES Email**
3. Confirm the sender is `i2g@g.ucmerced.edu`
4. Enter recipients, subject, body, and optional attachments
5. Send and verify the result in **SES Email Logs**
