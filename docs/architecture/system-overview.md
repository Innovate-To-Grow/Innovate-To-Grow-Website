# System overview

What the Innovate to Grow (I2G) website is, what it is made of, and how email, SMS, the admin console and the
website content fit together. It is written for program staff, UC Merced IT and new developers, and needs no coding
knowledge.

> **Public document.** This repository is public. This page names services and roles only. Account IDs, resource
> names and ARNs, hostnames of internal systems, IP addresses, credentials, contacts and ticket numbers belong in the
> **private ops doc** (see the [operations runbook skeleton](../deployment/ops-runbook.md)).

## What the system does

The I2G platform supports the School of Engineering's Innovate to Grow program at UC Merced:

- **Public website:** pages about the program, events and schedules, the projects catalog and past projects, news,
  and an AI assistant that answers questions about the program.
- **Member accounts:** people sign in with a one-time code sent to their email address or phone number, with a
  personal sign-in link from an email, or with a password if they set one. A member can have several email
  addresses and phone numbers.
- **Events:** registration, tickets sent by email, check-in at the event, and an optional copy of the registrations
  in a Google Sheet.
- **Communication:** email campaigns ("blasts") and SMS broadcasts to chosen audiences, plus sign-in codes, tickets
  and other notices sent by the system.
- **Admin console:** where staff manage members, events, website pages, campaigns and settings.

## The parts

```
 Visitors and members ──▶ Public website (React, served by AWS Amplify)
                                │  /api/
                                ▼
 Staff ──▶ /admin/ ────▶ Backend (Django web application, in containers on AWS)
 Developers ──▶ CLI ───▶   ├── PostgreSQL database ..... members, contacts, events, registrations, website pages,
                           │                              campaigns, email records, settings
                           ├── File storage (S3) ....... images and uploaded files
                           ├── Background worker ....... campaign sends, bounce scans, sheet syncs, clean-ups
                           └── Outside services
                                 ├── Microsoft Graph ............ sends email as i2g@ucmerced.edu; reads its Inbox
                                 ├── Amazon SES, SMTP, Gmail API  alternative email providers (one is active)
                                 ├── AWS End User Messaging ..... SMS codes and Broadcast SMS
                                 ├── Amazon Bedrock ............. AI assistant, AI search, scam second opinion
                                 ├── Google Sheets .............. members and registrations out; schedule, projects in
                                 ├── Gmail (IMAP) ............... email template import
                                 └── RSS feeds .................. news articles
```

| Part | What it does | Who uses it |
|---|---|---|
| Public website | The pages people see. A single-page React application; every piece of data comes from the backend | Visitors, members |
| Backend | One Django application: the API behind the website, the admin console, sign-in, campaigns, the scheduled work | Everyone, through the website or the admin |
| Admin console (`/admin/`) | Forms and dashboards for staff, organised by section in a sidebar | Staff with admin access |
| Background worker | A separate container that works through the job queue in the database: one job per campaign recipient, bounce scans every 10 minutes, Google Sheet syncs, hourly clean-ups | Nobody directly; staff see its results |
| Database | PostgreSQL. Holds all records, the job queue and most settings | The backend only |
| File storage | Amazon S3. Holds uploaded images and files, and the admin's static files | The backend; every uploaded file is public to anyone who has its link |
| `i2g-admin` CLI | Terminal access to records for developers, with the same per-section access as the admin; credentials, tokens and a few other sensitive tables are never available through it | Developers |
| Archive site | A small separate site that serves the event pages of past years | Visitors |

How a request travels from a browser to the database is described in [Request flow](request-flow.md), and the code
layout in [Repository structure](repository-structure.md).

## Where the data lives

| Data | Where | Kept |
|---|---|---|
| Members, their email addresses and phone numbers | Database; optionally copied to a Google Sheet (**Member Sheet Sync**: names, primary email and phone, organization, title, active) | Until the member or staff delete them |
| Event registrations, tickets, check-ins | Database; optionally copied to a Google Sheet | Until deleted |
| Website pages, menus, news | Database; images in S3 | Until deleted |
| Email and SMS campaigns and their recipient lists (addresses, phone numbers, status) | Database | Until deleted |
| Records of every email sent (who, when, provider answer) | Database ([Email monitoring](../integrations/email-monitoring.md)) | 180 days |
| Bounce reports read from the mailbox | Database | 365 days |
| The email messages themselves (received and sent) | The i2g@ucmerced.edu mailbox in Microsoft 365; the site reads them but does not store their text (the admin's inbox page caches what staff open for a few minutes; the planned helpdesk will store messages) | Mailbox policy |
| Website page views (path, IP address, a random browser ID) | Database | Until deleted (no automatic clean-up yet) |
| AI assistant and AI search conversations | Database, when **Public Assistant Audit Logging** is on | Set to 90 days, but deleted only when the clean-up command is run |
| Credentials | AWS Secrets Manager for the application's own secrets (such as the database password), the Microsoft Graph and Gmail API private keys and the shared AWS key; the other service credentials (for example the SMTP and Gmail passwords and the Google service-account key) in the database, under **Site Settings → Service Credentials** | Until rotated |
| Activity history (who changed what in the admin) | Database (Site Settings → Admin Log, and each record's History) | Until deleted |

Personal sign-in links are removed from anything the site stores about an email (subjects are scrubbed or kept
only as a fingerprint). Exports made from the admin contain personal data and should be kept in a restricted place.

## How email works

1. **One provider at a time.** Every email the site sends (sign-in codes, tickets, invitations, campaigns, replies
   from the admin inbox) goes through the provider selected under **Broadcast Delivery → Email Sending Method**:
   Microsoft Graph, Amazon SES, SMTP or the Gmail API. Today it is **Microsoft Graph**, sending as
   **i2g@ucmerced.edu**. There is no automatic fallback to another provider. (Only the test email on a provider's
   own settings page can go through a provider that is not selected.)
2. **Pacing.** Each provider has sending limits (for the Exchange mailbox: per minute and per day as set by UC
   Merced IT, and Microsoft's standard hourly limits). The site paces every send to stay under them and keeps part of
   the allowance for sign-in codes and tickets, so a large campaign takes hours, and a long list carries on the next
   day ([Delivery rates](../integrations/delivery-rates.md)).
3. **Campaigns.** A campaign resolves its audience when it is sent, then queues one job per recipient. The
   background worker sends them at the paced rate. If the message uses a personal sign-in link, each recipient
   with an account gets their own; others get a link to the sign-in page.
4. **"API accepted" is not "delivered".** Microsoft answers that it has *accepted* a message for delivery. The site
   records that answer, but it never learns that a message reached an inbox. It only learns about failures.
5. **Bounces.** When delivery fails, the receiving server sends a bounce report (an "undeliverable" message) back
   to i2g@ucmerced.edu. Every 10 minutes the background worker reads new bounce reports from that Inbox, without
   changing the mailbox, and records them. Staff see them on **Email Monitoring**. Nothing about a member changes
   because of a bounce unless a staff member decides it should.
6. **Replies.** Replies to campaigns, out-of-office notices and other mail also arrive in the i2g@ucmerced.edu
   Inbox. Staff read them in Outlook or in the admin's inbox page (**Broadcast Delivery → Gmail Inbox**, which shows
   the i2g@ mailbox when Microsoft Graph is set up to read it).

The site can read the i2g@ mailbox but cannot change it: it never moves, deletes, forwards or marks messages, and
its connection to Microsoft refuses every request except sending and reading. The app it uses authenticates with a
certificate, and UC Merced IT reports that it is restricted to the I2G mailbox; the status of that evidence is kept
in [Microsoft Graph email](../integrations/microsoft-graph-email.md).

## How SMS works

- Text messages go through **AWS End User Messaging**: sign-in and verification codes, the admin's test message
  and **Broadcast SMS** campaigns. US numbers only.
- People can sign up and sign in with a phone number alone; event registration can ask for a verified phone. Coming
  with pull request #732: only a verified number signs in, and a number becomes verified only with a code (from
  the member's account page, or staff's **Verify by SMS code** page with the member reading the code back).
- Coming with pull request #731: links in texts (off by default). A personal sign-in link goes only to the
  member's own verified phone, and switching personal links (or links in texts) off revokes every one already
  sent, for good.
- SMS sending is paced like email. A daily SMS limit can be set; none is set until it has been calibrated.
- The site only sends. It does not receive text messages, so replies such as STOP are not yet synced back to a
  member's phone settings.

## How the admin works

- **Access by section.** Each staff account is granted the sections ("apps") it may use, for example members
  (`authn`), campaigns and delivery (`mail`), events (`event`), website content (`cms`), projects (`projects`) and
  site settings and credentials (`core`). Within a granted section a staff member can view and change everything.
  The **I2G Master** account (superuser) has every section, and only it can grant access, change staff accounts,
  or make a few destructive changes.
- **Confirmation.** Saving a change, a bulk action and most risky operations show a summary first and ask you to
  type a confirmation word (sending a campaign asks for the campaign's name).
- **History.** Changes saved on a record's page, deletions and a few settings pages are recorded with who and when:
  on each record's **History** page and in **Site Settings → Admin Log**. Most bulk actions run from a list, the
  member import and replies from the inbox page are not recorded there; a campaign records who sent it.
- **The CLI** (`i2g-admin`) signs in through the admin and applies the same section grants.

The day-to-day tasks are described for staff in the [staff handbook](../staff/README.md).

## How the website content works

- Pages are built from **blocks** (text, images, tables, embeds, and so on) in **Content Management System → Page
  Content**, with a live preview. Menus, the footer, the home page and short **Route Redirects** are edited in the
  same section.
- **News** articles are imported from RSS feeds (**News Management**); the admin can correct an imported article.
- The **event schedule** with its current projects, and the **past-projects** catalog, are imported from Google
  Sheets.
- Site-wide style changes can be made without a deploy (design tokens and custom CSS; see
  [Theme and custom CSS](../cms-admin/theme-and-custom-css.md)).

See the [CMS & Admin guide](../cms-admin/index.md).

## Outside services and who owns them

| Service | Used for | Managed by |
|---|---|---|
| AWS (containers, database, file storage, SES, SMS, Bedrock, Amplify, Secrets Manager) | Hosting and most integrations | The I2G AWS account owner |
| Microsoft 365 / Entra (the i2g@ucmerced.edu mailbox and the app that sends from it) | Email | UC Merced OIT; I2G owns the mailbox |
| Google Workspace / Google Cloud | Sheets syncs, Gmail template import | I2G |
| GitHub | Code, reviews, automated tests and deploys | I2G web team |
| UC Merced DNS and campus network | The site's domain names, campus address ranges | UC Merced OIT |

Names, contacts, account numbers and ticket references for each service are in the private ops doc.

## Security and privacy at a glance

- No production passwords, keys or tokens are kept in code or in this repository (only throwaway defaults for a
  developer's own machine). Production secrets sit in AWS Secrets Manager; the two private keys used to send email
  can be read only by the running application.
- Sign-in uses one-time codes and personal sign-in links; links expire (7 days by default for campaigns) and can be
  revoked from the admin.
- Changes saved in the admin are attributed and logged (see **History** above); risky actions need a typed
  confirmation.
- Requests are rate-limited, and code requests carry a proof-of-work check (ALTCHA; required once **Send
  Verification** is switched to enforce), to protect sign-in and the email and SMS budgets.
- Email records are deleted after 180 days and bounce reports after 365 days.
- Automated tests check every change before it can be deployed, and every production deploy waits for a person's
  approval.

## Further reading

- [Staff handbook](../staff/README.md): step-by-step tasks in the admin.
- [Architecture](index.md): how the code is organised.
- [Deployment guide](../deployment/index.md) and the [operations runbook skeleton](../deployment/ops-runbook.md).
- [Integrations](integrations.md): every outside service in detail.
