# CMS and Admin Guide

This guide is for site administrators managing content through the Django admin interface.

## Accessing the Admin

Navigate to `/admin/` and log in with your staff account. The admin uses the Innovate to Grow theme with a sidebar for navigation.

### Sidebar Sections

| Section | What It Contains |
|---------|-----------------|
| CMS | CMS Pages |
| Site Settings | Home Page, Site Maintenance Control, Menus, Footer, Sheet Sources |
| Events | Events |
| News | News Articles, Feed Sources, Sync Logs |
| Projects | Semesters, Projects |
| Members | Members, Groups |
| Mail | Gmail API Accounts, Inbox, Sent Mail, Compose, SES Mail Senders, SES Compose, Email Logs, SES Email Logs |

---

## CMS Pages

CMS pages are the primary way to manage content on the website. Each page has a URL route, a status, and an ordered list of content blocks.

### Creating a Page

1. Go to **CMS > CMS Pages** and click **Add CMS Page**
2. Fill in the required fields:
   - **Slug** — Stable identifier for import/export. Use lowercase with hyphens (e.g., `about-us`). Do not change after publishing.
   - **Route** — The URL path where this page will appear (e.g., `/about`). Must start with `/`. Must be unique.
   - **Title** — Page title shown in the browser tab
3. Set **Status** to control visibility (see lifecycle below)
4. Add content blocks in the visual editor

### Page Status Lifecycle

| Status | Visibility | When to Use |
|--------|-----------|-------------|
| **Draft** | Not visible to the public. Staff can preview with `?preview=true`. | While building or editing content |
| **Published** | Visible to everyone at the page's route | When content is ready for the public |
| **Archived** | Not visible to the public | When a page is no longer needed but you want to keep it |

When a page is changed to Published for the first time, the `published_at` timestamp is set automatically.

### Page CSS Class

The **Page CSS Class** field lets you assign a CSS class to the page wrapper div. This enables per-page styling in the frontend. For example, setting `about-page` applies styles from `pages/src/components/CMS/page-styles/AboutPage.css`.

### Preview

Use the **Preview** button in the page editor to generate a temporary preview link. This creates a token-based URL that works for 10 minutes, even for draft pages. The preview opens in a new tab showing how the page will look on the live site.

### Import and Export

- **Export**: Select pages in the list view and use the "Export selected as JSON" action
- **Import**: Click "Import JSON" in the page list toolbar and upload a JSON file. A dry-run preview shows what will be created/updated before you confirm.
- **Import All Seeds**: Imports all predefined seed pages from management commands

---

## Content Blocks

Blocks are the building units of CMS pages. Each block has a type, a sort order, and a data payload specific to its type.

### Block Types

| Type | Description | Key Data Fields |
|------|-------------|-----------------|
| **Hero Banner** | Full-width banner with heading and optional image | heading, subheading, image_url, image_alt |
| **Rich Text** | Free-form HTML content | body_html, heading, heading_level |
| **FAQ List** | Expandable question/answer pairs | items (array of {question, answer}), heading |
| **Link List** | List of clickable links | items (array of {title, url}), heading, style |
| **CTA Buttons** | Call-to-action button group | items (array of {label, url, style}) |
| **Image + Text** | Image alongside text content | body_html, image_url, image_alt, image_position, heading |
| **Notice / Callout** | Highlighted message box | body_html, heading, style |
| **Contact Info** | Contact details list | items (array of {label, value, type}), heading |
| **Google Sheet Embed** | Renders data from a Google Sheet source | sheet_source_slug, sheet_view_slug, display_mode, heading |
| **Section Group** | Container for nested content sections | sections (array), heading |
| **Data Table** | Structured table with columns and rows | columns, rows, heading |
| **Numbered List** | Ordered list with optional preamble | items (array), heading, preamble_html |
| **Proposal Cards** | Card layout for project proposals | proposals (array), heading, footer_html |
| **Navigation Grid** | Grid of navigation cards/links | items (array of {title, url, description}), heading |
| **Schedule Grid** | Event schedule from a sheet source | sheet_source_slug, heading |

### Working with Blocks

- **Add**: Use the dropdown at the bottom of the block editor to select a type and click "Add Block"
- **Reorder**: Use the up/down arrow buttons on each block card
- **Collapse/Expand**: Click the block header to toggle visibility of its fields
- **Delete**: Click the delete button on the block card
- **Admin Label**: Set a label on any block to identify it in the collapsed view (e.g., "Hero — About Page")

---

## Menus

Menus control the site navigation. Go to **Site Settings > Menus** to manage them.

### Menu Items

Each menu item has:
- **Title** — Display text in the navigation
- **URL** — Where the link goes
- **Type** — How the URL is resolved:
  - `app` — Links to a data-driven page (e.g., `/news`, `/current-projects`)
  - `external` — Links to an external URL (opens in a new tab if configured)
  - `cms` — Links to a CMS page by its route
- **Children** — Sub-items displayed as a dropdown

The menu editor provides a visual interface with dropdowns for app routes and CMS pages. CMS pages are loaded dynamically from the database, so newly published pages appear automatically.

**Available app routes** (defined in `src/pages/app_routes.py`):
- `/news`, `/current-projects`, `/past-projects`, `/event`, `/schedule`, `/projects-teams`, `/acknowledgement`

---

## Footer

Go to **Site Settings > Footer** to manage footer content. Only one active footer is allowed (singleton).

The footer content is a JSON structure with:
- **CTA Buttons** — Call-to-action buttons displayed at the top of the footer
- **Contact HTML** — Contact information block
- **Columns** — Footer link columns, each with a title and list of links
- **Social Links** — Social media icon links
- **Copyright** — Copyright text
- **Footer Links** — Bottom-row links (e.g., Privacy Policy)

Use the visual editor to manage these sections. A "Raw JSON" toggle is available for advanced editing.

---

## Site Settings

Go to **Site Settings > Home Page** to configure the homepage behavior.

### Homepage Mode

| Mode | When to Use | Effect |
|------|-------------|--------|
| `pre-event` | Before an event | Homepage shows pre-event content |
| `during-semester` | During a regular semester | Homepage shows semester content |
| `during-event` | During a live event | Homepage shows event content; layout API prefetches sheet data |
| `post-event` | After an event | Homepage shows post-event content |

### Homepage Route

The **Homepage Route** field determines which page is displayed at `/`. Set it to a CMS page route (e.g., `/about`) or a data-driven page route (e.g., `/event`). The frontend's `HomepageResolver` reads this value from the layout API and renders the corresponding page.

---

## Google Sheet Sources

Go to **Site Settings > Sheet Sources** to connect Google Sheets for display on the site.

Each source needs:
1. **Slug** — Identifies the source in API calls and block references
2. **Spreadsheet ID** — The long ID from the Google Sheets URL
3. **Range** — Cell range in A1 notation (e.g., `Sheet1!A1:L100`)
4. **Sheet Type** — Determines how the data is parsed (see [Google Sheets Integration](events-sheet-sync.md))

After saving, data is available at `/sheets/<slug>/` and can be referenced in CMS blocks (Google Sheet Embed, Schedule Grid).

To force a cache refresh, use the admin action or the refresh API endpoint.

---

## Events

Go to **Events > Events** to manage event records.

Each event has:
- **Name** and **Slug** (auto-generated from name)
- **Date**, **Time**, **Location**
- **Description** (rich text)
- **Is Live** — Toggle to mark the event as currently active

Events can include:
- **Tickets** — Name, price, quantity, display order
- **Questions** — Custom questions, required flag, display order

Events are managed in the admin only. There are currently no public API endpoints for events — event data on the frontend is typically served via CMS pages and Google Sheets.

---

## News

### News Articles

Go to **News > News Articles** to view synced news. Articles are typically created by the sync process, not manually.

### Feed Sources

Go to **News > Feed Sources** to manage RSS feed connections. Each source has a feed URL and a source key. The default feed is the UC Merced news feed.

### Syncing

News articles are synced from RSS feeds using the `sync_news` management command:

```bash
python manage.py sync_news
```

This fetches new articles from all active feed sources, creates new records, and updates existing ones. It also scrapes article pages for full content and hero images.

**Sync Logs** (under News > Sync Logs) show the history of sync operations with counts and errors.

---

## Projects

### Semesters

Go to **Projects > Semesters** to manage semesters. Each semester has a year, season (Spring/Fall), and publication status.

Only published semesters are visible on the public site. The most recent published semester is shown as "Current Projects."

### Projects

Go to **Projects > Projects** to manage individual projects within semesters.

Projects can be managed in three ways:
1. **Manual creation** in the admin
2. **Import from Excel** — Upload an Excel file via the semester list page's "Import from Excel" button
3. **Sync from Google Sheets** — Use the "Sync from Sheets" button or run `python manage.py sync_projects`

---

## Mail

### Gmail API Accounts

Go to **Mail > Gmail API Accounts** to configure Gmail sending. This requires a Google Cloud service account with domain-wide delegation.

Only one active Gmail account is allowed. Provide the service account JSON and the delegated email address.

Use the "Test Connection" button to verify the setup.

### SES Mail Senders

Go to **Mail > SES Mail Senders** for AWS SES email configuration. SES credentials are configured via environment variables (`SES_AWS_ACCESS_KEY_ID`, etc.).

### Composing Email

- **Mail > Compose** — Send via Gmail API
- **Mail > SES Compose** — Send via AWS SES

Both support To, CC, BCC, subject, HTML body, and file attachments.

### Email Logs

**Mail > Email Logs** and **Mail > SES Email Logs** show audit trails of all sent emails with status, recipients, and timestamps.

---

## Members

### Member Management

Go to **Members > Members** to manage user accounts. Each member has:
- Email, username, name fields
- Organization
- Active member status
- Contact emails and phones
- Profile image (base64-encoded)
- Group membership

### Import from Excel

Use the "Import from Excel" button on the member list page to bulk-create members from a spreadsheet.

### Groups

Go to **Members > Groups** to manage permission groups for members.

---

## Common Pitfalls

- **Changing a CMS page route** after publishing will break any existing links or bookmarks to that URL. Update menu items and any cross-references if you change a route.
- **Changing a page slug** after export will cause re-imports to create duplicates instead of updating the existing page.
- **Draft pages are not visible** to regular users. Always set status to Published when content is ready.
- **Menu changes take up to 10 minutes** to appear on the live site due to caching. Save the menu to force cache invalidation.
- **Sheet source slug changes** will break any CMS blocks that reference the old slug. Update all Google Sheet Embed and Schedule Grid blocks if you rename a source.
- **Only one active footer/Gmail account/SES account** is allowed. Activating a new one automatically deactivates the previous one.
- **Homepage route must match an existing page** route or app route. Setting it to a non-existent route will show a blank homepage.
