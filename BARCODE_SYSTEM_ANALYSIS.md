# Barcode System and Admin Analysis - Findings Report

## 1. Barcode Generation and Payload Format

### Barcode Payload Structure
**File:** `src/event/models/registration/registration.py` (lines 76-77)
```python
@property
def barcode_payload(self):
    return f"I2G|EVENT|{self.event.slug}|{self.ticket_code}"
```

**Format:** `I2G|EVENT|{event_slug}|{ticket_code}`
- **Example:** `I2G|EVENT|autumn-networking-2025|I2G-ABC123DEF456`

### Barcode Generation Process
**File:** `src/event/services/ticket_assets.py` (lines 78-83)
- Uses PDF417 barcode format (configured in `src/event/models/registration/ticket.py` line 18)
- `generate_ticket_barcode_png_bytes()` calls `pdf417gen` library with:
  - `columns=6`
  - `scale=3`
  - `ratio=3`
  - `padding=10`
- Renders PNG image and returns byte data
- `generate_ticket_barcode_data_url()` base64-encodes PNG for data URL usage

## 2. Ticket Code Generation

**File:** `src/event/models/registration/registration.py` (lines 9-10)
```python
def generate_registration_ticket_code():
    return f"I2G-{secrets.token_hex(6).upper()}"
```

**Format:** `I2G-{12-char-uppercase-hex}` (e.g., `I2G-A1B2C3D4E5F6`)
- Auto-generated using `secrets.token_hex(6)` → 12 hex characters
- Stored in `ticket_code` field (CharField, max_length=24, unique=True)
- Has an index for fast lookups

## 3. Database Model Structure

### EventRegistration Model
- **Primary Key:** `id` (UUID from ProjectControlModel)
- **Fields:**
  - `member` (FK to auth user) - the person who registered
  - `event` (FK to Event)
  - `ticket` (FK to Ticket)
  - `ticket_code` (unique, indexed) - **key for lookups**
  - `attendee_*` fields (name, email, phone, organization)
  - `question_answers` (JSONField)
  - `ticket_email_sent_at`, `ticket_email_error`
- **Index:** `fields=["ticket_code"]` for fast barcode-to-registration lookup

### Related Models
- **Event:** name, slug, date, location, is_live, registration settings
- **Ticket:** FK to Event, name, barcode (UUID, different from ticket_code), order

### Unique Constraints
- `unique_event_registration_per_member` - one registration per member per event
- `ticket_code` - globally unique per registration

## 4. Existing Admin Structure

### EventAdmin (`src/event/admin/event.py`)
- Uses **Unfold** admin theme (Django admin enhancement)
- **Custom change form template:** `admin/event/event/change_form.html`
  - Extends `admin/change_form.html`
  - Displays service configuration status (Email, SMS, Google)
- **Inlines:** TicketInline, QuestionInline
- **Actions:** sync_registrations_to_sheet
- **Readonly fields:** created_at, updated_at, sheet sync status
- **Fieldsets:** Event Details, Registration Form Options, Google Sheet, System

### EventRegistrationAdmin (`src/event/admin/registration.py`)
- **List display:** ticket_code, attendee names/emails, phone, ticket, event, created_at
- **Search fields:** attendee info, ticket_code
- **All fields are readonly** (lines 32-49)
- **Permissions restricted:**
  - `has_add_permission()` = False
  - `has_change_permission()` = False
  - `has_delete_permission()` = True (can only delete, not edit)
- **Fieldsets:** Attendee, Ticket, Questions & Answers, Email Status, System
- Used for viewing/deleting registrations only, not editing

### BaseModelAdmin
- Located at `src/core/admin/base.py`
- Extends Unfold's `ModelAdmin`
- Includes `SoftDeleteAdminMixin` and `TimestampedAdminMixin`
- Common readonly fields: `id`, `created_at`, `updated_at`
- Default list_per_page = 50

## 5. Existing Barcode-Based Lookup

### Ticket Login View (`src/event/views/ticket_login.py`)
- **TicketAutoLoginView** - handles ticket email login token exchange
- **NOT a barcode scanner lookup** - it's for email token-based login
- Uses `get_member_from_login_token()` which validates signed tokens

### Available Helper Functions in `src/event/services/ticket_assets.py`
- `build_ticket_access_token(registration)` - creates signed token with registration_id
- `get_registration_from_access_token(token)` - validates and retrieves registration by token
- `build_ticket_login_token(member)` - creates signed login token
- `get_member_from_login_token(token)` - validates and retrieves member by token
- **No existing barcode payload parser** - would need to be created

## 6. Admin Customization Patterns

### Existing Custom Admin Templates
- **Location:** `src/event/templates/admin/event/event/change_form.html`
- **Pattern:** Extends Django admin base template and overrides blocks
- **Approach:** Adds custom HTML blocks to display configuration status
- **Uses:** Unfold CSS classes (rounded-default, border, dark mode support)

### Admin Extensibility Options
1. **Custom change_form_template** - override form rendering
2. **Custom change_list_template** - override list view
3. **readonly_fields** - add computed properties
4. **Custom actions** - add batch operations
5. **Custom templates directory** - `app/templates/admin/appname/modelname/`

## 7. Barcode Scanner Implementation Requirements

### To implement barcode scanner in admin:

1. **Parse barcode payload**
   - Extract format: `I2G|EVENT|{event_slug}|{ticket_code}`
   - Validate structure

2. **Lookup registration**
   - Query: `EventRegistration.objects.get(ticket_code=scanned_ticket_code)`
   - Filter by event (optional, from barcode slug)

3. **Admin integration options**
   - Add barcode scanner form to EventRegistrationAdmin change_list_template
   - Add custom action for scanning
   - Add inline barcode input with lookup
   - Create separate admin page for check-in

4. **Key database query**
   ```python
   registration = EventRegistration.objects.select_related(
       'event', 'ticket', 'member'
   ).get(ticket_code=ticket_code)
   ```

5. **Admin template location**
   - `src/event/templates/admin/event/eventregistration/change_list.html`

## 8. Key Files Summary

| File | Purpose | Key Info |
|------|---------|----------|
| `registration.py` (models) | EventRegistration model | barcode_payload property, ticket_code generation |
| `ticket_assets.py` | Barcode generation | PDF417 encoding, PNG rendering |
| `event.py` (admin) | Event admin interface | Custom template pattern |
| `registration.py` (admin) | Registration admin | Read-only pattern, permissions |
| `ticket_login.py` | Token-based login | Signed token pattern (not barcode) |
| `base.py` (core admin) | Base admin class | Unfold integration, mixins |

## 9. Barcode Lookup Query Pattern

To look up a registration from scanned barcode:

```python
# Parse barcode: "I2G|EVENT|event-slug|I2G-ABC123DEF456"
parts = barcode_payload.split('|')
event_slug = parts[2]
ticket_code = parts[3]

# Query
registration = EventRegistration.objects.select_related(
    'event', 'ticket', 'member'
).get(ticket_code=ticket_code)

# Validate (optional)
if registration.event.slug != event_slug:
    raise ValueError("Barcode event mismatch")
```

The ticket_code lookup is fast because:
- It's indexed in the model
- It's globally unique
- EventRegistration has high query volume

## 10. Unfold Admin Theme Integration

- Uses Material Design 3 with Tailwind CSS
- Custom icon library: Material Symbols Outlined
- Dark mode support with Tailwind dark: prefix
- Common CSS classes: rounded-default, border-base-200, text-primary-600
- Extends base admin templates following Django pattern
