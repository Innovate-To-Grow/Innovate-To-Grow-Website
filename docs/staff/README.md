# Staff handbook

Step-by-step help for I2G staff and student assistants who use the admin console (`/admin/`). No coding knowledge
is needed. For how the system is built, see the [System overview](../architecture/system-overview.md).

> **This handbook is public** (it lives in a public GitHub repository). Never add member names, real email
> addresses, phone numbers, screenshots that show personal data, account numbers, passwords or ticket references.
> Use made-up examples such as `jane.doe@example.edu`.

## Chapters

| # | Chapter | Status |
|---|---|---|
| 1 | Getting started | Planned |
| 2 | [Members & import](02-members-and-import.md) | **Written** |
| 3 | [Blasts & email monitoring](03-blasts-and-email-monitoring.md) | **Written** |
| 4 | Replies, the i2g@ Inbox and the helpdesk | Planned: after the helpdesk ships |
| 5 | SMS | Planned: after the SMS compliance work ships |
| 6 | Events | Planned |
| 7 | Website content | Planned |
| 8 | FAQ & troubleshooting | Planned |

### 1. Getting started (planned)

- Signing in to the admin, and what to do when a code does not arrive.
- The sidebar: **Content Management System**, **Events**, **Projects**, **Members & Authentication**, **Broadcast
  Delivery**, **System Intelligence**, **Site Settings**, **CLI Admin**. You see only the sections you were given.
- Access: each staff account is granted sections ("apps"); the **I2G Master** account has all of them. Who to ask
  for access.
- The confirmation step: before a change is saved the admin lists what will change and asks you to type a word.
- **History** on every record, and **Site Settings → Admin Log**.
- Personal data: exports, downloads and screenshots.

### 2. Members & import (written)

Finding and editing members, email roles (primary, secondary, other), verified and subscribed, exporting, and
importing a spreadsheet, including why a row is skipped ("Row 5") and the review step that is coming.

### 3. Blasts & email monitoring (written)

Writing, testing and sending a broadcast email, choosing the audience, personal sign-in links, what "API accepted"
means, the Email Monitoring dashboard, bounce reports, reading older reports again, and the Bounced addresses page.

### 4. Replies, the i2g@ Inbox and the helpdesk (planned)

To be written once the helpdesk is live (it starts in a "shadow" mode in which it records tickets and sends
nothing):

- Where replies to blasts go, and reading them in Outlook or in the admin's inbox page.
- The helpdesk: every message to i2g@ucmerced.edu becomes a ticket. Automated mail (out-of-office replies, bounce
  reports, read receipts, newsletters, spam) becomes a ticket that is closed at once and hidden by default; a message
  from a person, or one the system is unsure about, becomes a normal ticket.
- Working a ticket: status, assignee, notes, linking a member; what shadow mode does not do yet (no replies, no
  notifications).
- The scam warning shown on suspicious messages.

### 5. SMS (planned)

Phone sign-up and sign-in, Broadcast SMS audiences and wording, consent and STOP, message length and cost, the SMS
log.

### 6. Events (planned)

Setting up an event and its registration form, tickets and their sign-in links, check-in on the day, the Google
Sheet copy of registrations, exports, and emailing registrants.

### 7. Website content (planned)

CMS pages and blocks with live preview, menus, footer and home page, short links (**Route Redirects**) and QR codes,
news feeds, the schedule and projects imports, style changes.

### 8. FAQ & troubleshooting (planned)

Collected from the chapters as questions come in.

## Words used in this handbook

| Word | Meaning |
|---|---|
| Member | One person's account. Each member has a **Member UUID**, a long ID shown on the member page and in exports. |
| Contact email | An email address saved on a member. An address belongs to one member at most. An address with no member is an **unlinked contact**. |
| Primary / secondary / other | The role of an email address. A member's main address is the **primary**; their other addresses are **secondary** (a backup) or **other** (often an old primary). |
| Verified | The person proved the address or phone number is theirs by entering a code (or staff marked it verified). Only verified addresses and numbers can be used to sign in. |
| Subscribed | Set per address and per phone number. For an email address: whether it receives newsletters (the **All subscribers** audience); the unsubscribe link in a newsletter turns it off for every address of that member. For a phone number: whether it receives SMS sent to subscribers. |
| Active / inactive | An inactive member cannot sign in and is left out of the **All subscribers** and **All active members** audiences. Their history stays. |
| Unfinished sign-up | Someone started creating an account and never finished. |
| Staff / I2G Master | A staff account can open the admin, limited to the sections it was granted. The I2G Master account (superuser) can do everything, including changing other staff accounts. |
| Campaign, blast | An email sent from **Broadcast Email** to an audience. |
| Audience | Who a campaign goes to, for example **All subscribers** or **Event registrants**. |
| Login link | `{{login_link}}` in a campaign: a personal link that signs that recipient in. Treat it like a password. |
| API accepted | Microsoft accepted the email for delivery. It is **not** proof that it was delivered. |
| Bounce report | The "Undeliverable" message a mail server sends back when it cannot deliver an email. |
| Suppressed, undeliverable | Coming soon: an address staff marked so that campaigns skip it. |

## Conventions

- **Bold** text is a label you will see on screen: a menu, tab, button or field.
- "Sidebar → Section → Tab" gives the path to a page.
- **Needs:** says which section access a task requires.
- "Coming soon" boxes describe changes that are built but not live yet. Their details may still change.

## Keeping this handbook current

- **Owner:** the I2G web developer writes and updates chapters; the I2G program lead reviews them.
- Any change to the code that changes what staff see in the admin updates the matching chapter in the same pull
  request.
- Re-read each chapter at the start of every term and fix what has changed. Screenshots, when added, are taken with
  test accounts only.
- Operational values (accounts, contacts, credentials, expiry dates of keys) do not belong here: see the
  [operations runbook skeleton](../deployment/ops-runbook.md) and the private ops doc.
