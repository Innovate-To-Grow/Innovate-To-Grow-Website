# CMS & Admin Panel Guide

This guide covers how to use the Django admin panel to manage website content, including pages, components, forms, events, and email broadcasts.

## Admin Access

The admin panel is available at `/admin/` and uses the [Django Unfold](https://github.com/unfoldadmin/django-unfold) theme (light mode only).

**Login**: Use your email address or username. The login form uses `EmailAdminAuthenticationForm`.

**Creating an admin user**: In development, run `python manage.py createsuperuser`. In production, the superuser is auto-created/updated by `entrypoint.sh` using the `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD`, and `DJANGO_SUPERUSER_EMAIL` environment variables.

## Admin Sidebar Navigation

The sidebar is organized into these sections:

| Section | Items |
|---------|-------|
| **Content Management** | Pages, Home Pages, Components, Google Sheets, Media, Forms, Submissions |
| **Layout** | Menus, Footer |
| **Events** | Events, Programs, Tracks, Ticket Options, Questions, Registrations |
| **Members** | Members, Groups |
| **MobileID** | Barcodes, Mobile IDs, Transactions |
| **Email & Notifications** | Gmail Accounts, Email Templates, Email Layouts, Broadcasts |

---

## Managing Pages

### Pages

Each page has:

- **Title**: Display name shown in the browser tab and navigation
- **Slug**: URL path (e.g., `about` → `/about`, `legacy/team` → `/legacy/team`). Supports nested paths.
- **Components**: Ordered list of `PageComponent` objects attached via the `PageComponentPlacement` through table
- **SEO fields**: Meta title, meta description, OG image
- **Publishing status**: Draft → Review → Published. Only published pages are visible to the public.

### Home Page

The home page is a separate model that allows multiple versions:

- Only **one** home page can be active at a time. Setting a new one as active automatically deactivates the previous one.
- The active home page is served at `GET /pages/home/`.
- Like regular pages, it has an ordered list of components.

### Preview

The admin provides a live preview feature:

- **Preview Popup**: Available at `/admin/preview-popup/` for full-page preview
- **Component Preview**: Available at `/admin/component-preview/` for individual component preview
- Preview data is exchanged via the `/pages/preview/data/` endpoint using preview tokens

---

## Page Components

Components are the building blocks of pages. Each component has a **type** that determines how it renders.

### Component Types

| Type | Description | Key Fields |
|------|-------------|------------|
| `html` | Raw HTML content | `html_content` |
| `markdown` | Markdown content (rendered as HTML) | `html_content` |
| `form` | Embedded form | `form` (FK to UniformForm) |
| `table` | Data table | `html_content` |
| `google_sheet` | Live Google Sheet data | `google_sheet` (FK), `google_sheet_style` |

### Component Fields

Every component can optionally include:

- **Hero image**: `image`, `image_alt`, `image_caption`, `image_link`
- **Background image**: `background_image`, `background_image_alt`
- **Custom CSS**: `css_file` (uploaded file) or `css_code` (inline CSS)
- **Custom JavaScript**: `js_code` (inline JS)
- **Data source**: `data_source`, `data_params`, `refresh_interval_seconds`, `hydrate_on_client` for dynamic data
- **Enabled flag**: `is_enabled` — disabled components are hidden from the frontend

### Component Placement

Components are attached to pages (or the home page) through the `PageComponentPlacement` model, which provides:

- **Order**: Controls the display sequence on the page
- **Reusability**: The same component can appear on multiple pages with different ordering

To add a component to a page, create a `PageComponentPlacement` linking the component to the page with the desired order number. Order values must be unique per page.

### CSS Scoping

CSS defined on a component is **automatically scoped** by the frontend renderer. All CSS rules are prefixed with `.component-{componentId}` so styles from one component cannot leak into another.

- Regular CSS rules get the scoped prefix prepended
- `@`-rules (e.g., `@media`, `@keyframes`) are left unscoped
- Comma-separated selectors are each individually scoped

**Example**: If you write `.title { color: red; }`, it becomes `.component-abc123 .title { color: red; }` at render time.

### JavaScript Sandboxing

JavaScript code runs in a **sandboxed iframe** with only the `allow-scripts` permission. This means:

- JS code **cannot** access the parent page's DOM
- JS code **cannot** make network requests
- JS code executes as an IIFE and receives a `root` element parameter
- Communication back to the page happens via `postMessage()`
- Errors are logged to the console but do not break the page

---

## Google Sheets Integration

Google Sheets can be embedded in pages as live data tables.

### Setting Up a Sheet

1. Create a `GoogleSheet` record in admin with:
   - **Spreadsheet ID**: The ID from the Google Sheets URL (`https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/...`)
   - **Sheet name**: The specific tab/worksheet name
   - **Range (A1 notation)**: Optional range like `A1:Z100` to limit the data
   - **Cache TTL**: How long to cache the data (default 300 seconds)
   - **Enabled**: Must be checked for public access

2. Create a `PageComponent` with type `google_sheet` and link it to the Google Sheet record.

3. Choose a **table style**: `default`, `striped`, `bordered`, or `compact`.

**Prerequisites**: The `GOOGLE_SHEETS_CREDENTIALS_JSON` environment variable must contain valid service account credentials, and the target spreadsheet must be shared with the service account email.

---

## Media Assets

Upload and manage images, documents, and other files:

- **Upload**: Via the admin media library or the `POST /pages/upload/` API endpoint (staff only)
- **Storage**: Local filesystem in development, S3 in production
- **Fields**: Original filename, MIME type, file size, alt text, upload timestamp
- **Usage**: Reference media URLs in component HTML content or use the image fields on components

---

## Forms (UniformForm)

The form builder creates dynamic forms without code changes.

### Creating a Form

1. **Name/Slug**: Internal name and URL identifier
2. **Fields**: JSON array defining the form fields. Each field has:
   - `type`: Input type (text, email, select, checkbox, textarea, etc.)
   - `label`: Display label
   - `name`: Field name in submission data
   - `required`: Whether the field is mandatory
   - `options`: Choices for select/radio fields
   - `validation`: Validation rules
3. **Submit button text**: Customize the button label
4. **Success message**: Shown after successful submission
5. **Redirect URL**: Optional URL to redirect after submission

### Form Settings

| Setting | Description |
|---------|-------------|
| `is_active` | Whether the form accepts submissions |
| `published` | Whether the form is publicly visible |
| `allow_anonymous` | Allow submissions without login |
| `login_required` | Require authentication to submit |
| `max_submissions_per_user` | Limit submissions (0 = unlimited) |

### Email Notifications

Enable `enable_email_notification` and set `notification_recipients` (comma-separated emails) to receive an email for each submission. Customize the subject with `email_subject_template`.

### Viewing Submissions

Submissions are accessible in the admin under **Content Management > Submissions**. Each submission has:

- **Status**: Pending → Reviewed → Processed → Archived (or Spam)
- **Data**: JSON object with all submitted field values
- **Metadata**: IP address, user agent, referrer, timestamp
- **Admin notes**: Internal notes field for reviewers
- **Review tracking**: Who reviewed it and when

---

## Event Management

### Events

Create and manage events with:

- Event name, date/time, bullet points
- Published flag for public visibility
- Live flag for export API eligibility
- Expo and reception table data (JSON arrays)

### Schedule Hierarchy

Events have a three-level schedule structure:

```
Event
  └── Programs (e.g., "Morning Session")
        └── Tracks (e.g., "Track A" in "Room 101")
              └── Presentations (ordered, with team info)
```

### Registration

Events support a registration flow with:

- **Ticket Options**: Define available ticket types
- **Questions**: Custom registration form questions
- **OTP Verification**: Email-based verification for registrants
- **Status Tracking**: Track registration status per attendee

### Google Sheets Sync

Events can be synced bidirectionally with Google Sheets. See [Events Sheet Sync](events-sheet-sync.md) for full API documentation.

---

## Email System

### Gmail Accounts

Configure Gmail accounts for sending emails. Used by the notification system.

### Email Layouts

Define reusable HTML email wrapper layouts (header, footer, styling).

### Email Templates (Message Layouts)

Create email content templates that are inserted into layouts. Templates can include dynamic variables.

### Broadcasts

Send bulk emails to member groups:

1. Select a **message layout** (template)
2. Choose an **email layout** (wrapper)
3. Select target **member groups** or individual recipients
4. Preview and send

---

## Cache Behavior

Content changes trigger cache invalidation automatically. The following caches are used:

| Content | Cache Key Pattern | TTL |
|---------|------------------|-----|
| Page data | Per-slug | 5 minutes |
| Active home page | Single key | 5 minutes |
| Footer content | Single key | 5 minutes |
| Layout (menus + footer) | Single key | 5 minutes |
| Google Sheet data | Per-sheet | Configurable (default 300s) |

**Manual invalidation**: Re-saving a page, home page, or footer in the admin triggers cache invalidation. For Google Sheets, the cache expires naturally based on the configured TTL.

---

## Tips

- **Component reuse**: Create a component once and attach it to multiple pages via separate placements with different order values.
- **Draft workflow**: Use the publishing status (Draft → Review → Published) to prepare content before making it live.
- **Preview**: Use the admin preview feature to see how changes look before publishing.
- **Nested slugs**: Pages support nested URL paths (e.g., `legacy/about`) — just enter the full path as the slug.
- **Soft delete**: Deleting records in admin performs a soft delete. Records can be restored if needed. Use `all_objects` manager in Django shell to find soft-deleted records.
