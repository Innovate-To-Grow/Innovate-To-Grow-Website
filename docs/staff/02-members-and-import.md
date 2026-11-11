# Chapter 2: Members & import

How to find and edit members, what the email roles and flags mean, and how to export and import members with a
spreadsheet. [Back to the handbook](README.md).

**Needs:** the Members section (**Members & Authentication** in the sidebar; `authn` in the access list). Changes
to a staff or superuser account need the I2G Master account.

All examples use made-up people and addresses.

## 2.1 What a member record holds

Open **Members & Authentication → Members** and click a name. The page has:

- **Member Info:** the **Member UUID**, the member's permanent ID. It is also the first column of an export.
- **Personal Info:** first, middle and last name, organization, title, profile image.
- **Permissions** (folded): **Active**, whether a self-service sign-up is still unfinished (read-only), the staff
  flag, and the sections a staff account may use. Only the I2G Master can change the last two.
- **Contact Emails:** every email address of the member, each with its **type**, **Verified** and **Subscribe**.
- **Contact Phones:** phone numbers (US only), each with **Verified** and **Subscribe**.
- **History** (top right): every change made in the admin, with who made it and when.

### Email addresses: role, verified, subscribed

| | What it means | Where it matters |
|---|---|---|
| **Primary** | The member's main address. (A member who signed up with a phone number may have no email address at all.) | Campaigns sent to "primary only"; a new event registration copies the primary address at the time of registering. |
| **Secondary** | A backup address, often added during event registration or on the account page. | Campaigns sent to "all emails"; sign-in if verified. |
| **Other** | Any further address, often a previous primary. | As secondary. |
| **Verified** | The person entered a code sent to that address, or staff marked it verified. | Only a verified address (or phone number) can be used to sign in. Only a verified address can become primary. |
| **Subscribe** | This address receives newsletters (**All subscribers** campaigns). | Set per address. Turning off one address leaves the others as they are. The unsubscribe link in a newsletter turns off every address of that member. |

An address can belong to one member only. An address can also exist with no member at all (an **unlinked
contact**), for example one entered by hand or left over from old data.

## 2.2 Find a member

1. Go to **Members & Authentication → Members**.
2. Type in the search box. It searches every email address of every member (primary, secondary and other), names,
   organization, title and the Member UUID.
3. Narrow the list with the filters **Active**, **Staff** and **Date joined**.

To find an address that may belong to nobody, use **Members & Authentication → Emails & Phones → Emails** and search
for it. An unlinked contact has an empty member column. The filters there show addresses by type, verified and
subscribed.

## 2.3 Change a member

Edit the fields, then **Save**. The admin shows a table of what will change and asks you to type a confirmation
word. Check the table, type the word, and confirm.

| Task | How |
|---|---|
| Fix a name, title or organization | Edit the field on the member page and save. |
| Add an address | Add a row under **Contact Emails** and save. Leave **Verified** unticked: the member verifies the address from their account page. |
| Make another address the primary | **Emails & Phones → Emails**, tick that one address, choose the action **Make selected email primary**, then **Run**. The address must be verified. The old primary becomes secondary and the old secondary becomes "other"; nothing is deleted. The primary itself cannot be edited or deleted directly. |
| Unsubscribe one address | Untick **Subscribe** on that address and save, or use **Toggle subscription status** on the Emails list. Re-subscribe an address only when the person asked for it. |
| Mark an address verified | **Emails & Phones → Emails** → **Mark selected emails as verified**. Do this only when you are sure the address belongs to this person: a verified address can sign in to their account. |
| Stop someone from signing in | **Members**, tick the member, action **Deactivate selected members**. Undo with **Activate selected members**. |
| Remove a member | Deactivate instead. Deleting a member is permanent and also deletes their event registrations and check-ins. |

On staff and superuser accounts, contact changes made by anyone other than the I2G Master are skipped with "only an
I2G Master may change those".

Changing a member's primary address does not change event registrations they made earlier: those keep the address
they were made with.

## 2.4 Export members

- **Members → Export Excel** downloads every member you can see.
- To export some members only, tick them and choose **Export selected members to Excel** (or **… as vCard**).

The file has these columns: Member UUID, First Name, Last Name, Middle Name, Title, Organization, Active, Staff, When
Started, Primary Email, Primary Verified, Primary Subscribed, Secondary Email, Secondary Verified, Secondary
Subscribed, Phone Number, Phone Subscribed, Phone Verified.

- It shows one secondary address per member. A member with more addresses has the others only in the admin.
- A cell that starts with `=`, `+`, `-` or `@` gets a leading apostrophe so spreadsheet programs do not treat it as
  a formula.
- **The file contains personal data.** Keep it in a restricted folder, do not email it around, and delete it when
  you are done.

## 2.5 Import members

The import adds new members from a spreadsheet and, if you ask it to, updates existing members.

> **Check which version is live first.** This section describes the safe import (pull request #726). On the
> **Import Members from Excel** page, the instructions box should say "Updates never delete anything". If it does
> not, the older import is still live, and with **Update Existing Members** ticked it *deletes* secondary addresses
> and phone numbers when their cells are blank, overwrites phone numbers, re-subscribes addresses and changes
> **Active**. Until the safe import is live, either leave **Update Existing Members** unticked, or delete from your
> sheet every column you do not mean to change, keeping only **Primary Email** and the columns to update.

### Steps

1. Go to **Members & Authentication → Members** and click **Import Excel**.
2. Optional: click **Download Import Template** for an empty sheet with the right column names and an Instructions
   tab. A sheet made with **Export Excel** works too.
3. Fill in one person per row. The first row holds the column names, so the first person is **row 2**.
4. **Excel File:** choose the file. It must be `.xlsx` (save older `.xls` files as `.xlsx` first) and at most 5 MB.
   Save the file with the members tab open: the import reads the tab that was open when the file was saved.
5. **Default Password:** leave it empty. New members then get a random password and sign in with a code. A shared
   default password would let anyone who knows a member's address sign in as them.
6. **Update Existing Members:** tick it only if the sheet should also update people who already have an account.
   Without the tick, rows for existing members are skipped.
7. Click **Start Import**.
8. Read the result: the counts (**Created**, **Updated**, **Skipped**, **Errors**, **Notes**), the list **Not
   imported, and why**, and the list **Imported, with notes: what was kept or not applied**. Each line has an
   **Open member** link when it is about a member.

The import sends no email and no SMS.

### Columns

Only **Primary Email** is required. A column that is missing, or a blank cell, never changes anything stored.

| Column | New member | Existing member (with **Update Existing Members**) |
|---|---|---|
| Primary Email | Becomes the member's primary address. | Finds the member (see "How rows are matched"). Never changed. |
| First Name, Last Name | Required for a new member. | A filled cell replaces the stored name. |
| Middle Name, Title, Organization | Optional. | A filled cell replaces the stored value. |
| When Started | Sets the date joined (default: today). | Ignored. |
| Primary Verified | Default FALSE. | TRUE marks the primary verified. FALSE never un-verifies it (a note says so). |
| Primary Subscribed | Default TRUE. | FALSE unsubscribes the primary. TRUE never re-subscribes it (a note says so). |
| Secondary Email | Added as the secondary address. | Added as the secondary; the previous secondary becomes "other". It starts unverified, and it is subscribed only if the member is subscribed at another address. |
| Secondary Verified, Secondary Subscribed | Used for the new secondary. | Not applied to an address the member already has (a note says so). |
| Phone Number | Added (10-digit US number). | Added next to the member's numbers, unverified. It never replaces a number. |
| Phone Verified, Phone Subscribed | Used for the new number (defaults: FALSE, FALSE). | Not applied to a number the member already has. |
| Active | Default TRUE. | Ignored. Use the **Activate** / **Deactivate** actions on the member list. |
| Staff | Ignored: an import never creates a staff account. | Applied only when the I2G Master imports. |
| Member UUID | Ignored by today's import. | Ignored (the coming review step uses it, see 2.6). |
| Last Updated, Primary Expired, Secondary Expired, Secondary Bounced | Accepted, not stored. | Same. |

TRUE/FALSE cells accept `TRUE`, `FALSE`, `Yes`, `No`, `Y`, `N`, `1` and `0`. Any other text (for example "N/A") is
ignored and reported, never read as FALSE.

### How rows are matched

- A row is matched to an existing member **only through that member's primary address**. Letter case does not
  matter.
- If the Primary Email exists in any other way (as somebody's secondary or "other" address, as an unlinked contact,
  or as two records that differ only in letter case), the row is **not imported** and the result says why and whose
  address it is.
- Two rows with the same Primary Email: only the first is imported.

### What an import never does

- Delete an address or a phone number.
- Move an address or a phone number from one member to another.
- Re-subscribe an address, or un-verify one.
- Activate or deactivate an existing member, or change staff status (unless the I2G Master imports).
- Send an email or a text message.

### Rows that were not imported

| Message (start) | What it means | What to do |
|---|---|---|
| "no member has … as their primary email: it is the **secondary** (or **other**) email of …" | The address belongs to a member, but it is not their primary. This is the "Row 5" case below. | Use the member's primary address in the Primary Email cell, or make this address their primary first (2.3). Then import that row again. |
| "… it is a contact email that is not linked to any member" | The address exists with no member. | In **Emails**, link it to the right member or delete it, then import again. |
| "… matches 2 contact emails that differ only in letter case" | Old duplicate records of the same address. | Ask the web team to merge them, then import again. |
| "Member with email … already exists: … Skipped because "Update Existing Members" is off" | The person already has an account. | Import again with **Update Existing Members** ticked, if you meant to update them. |
| "You do not have permission to update …" | A staff or superuser account. | Ask the I2G Master. |
| "Missing primary email", "Primary Email '…' is not a valid email address" | The cell is empty or not an address. | Fix the cell. |
| "Missing first name", "Missing last name" | A new member needs both names. | Fill them in. |
| "Duplicate email in file (…): row N has it too, and only that row is imported" | The same person is in the sheet twice. | Keep one row. |
| "… is already used by row N of this file" | Another row uses this address as its Secondary Email. | Decide which person the address belongs to. |
| "could not update …: … Nothing in this row was changed" | Something unexpected went wrong on that row. | Send the message to the web team. |
| "Error creating members: …" | No new member was created at all. | Send the message to the web team. |

### Notes on imported rows

Notes say what a row asked for that was not applied, or what was kept. They are information, not errors. For
example:

- "Secondary Email is blank; kept … (an import never deletes a contact)"
- "Primary Subscribed is TRUE, but … is unsubscribed; left unsubscribed (an import never re-subscribes)"
- "Added … as the secondary email; kept the previous secondary … as "other""
- "… was added unverified (contacts added to an existing member start unverified; …)"
- "Phone Number … belongs to …; not added (an import never moves a contact from one member to another)"
- "Active column ignored: the member stays active (…)"
- "Primary Verified cell 'N/A' is not TRUE or FALSE; it was ignored"

### Example: "Row 5"

Row numbers are spreadsheet rows: the column names are row 1, so row 5 is the fourth person. Suppose row 5 of the
sheet is Jane Doe with `jane.doe@partner.example` in **Primary Email**, and **Update Existing Members** is ticked. The
result says:

> Row 5: no member has jane.doe@partner.example as their primary email: it is the secondary email of Jane Doe
> (member 1b2c3d4e-…), whose primary email is jdoe@example.edu. Row not imported. Rows are matched to existing
> members by primary email only: put the member's primary email in the Primary Email cell, or make this address
> their primary email on the member page first

Nothing about Jane changed. To finish:

1. Click **Open member** and check that this is the same Jane Doe.
2. Decide which address should be her primary:
   - **Keep `jdoe@example.edu`:** change the Primary Email cell of row 5 to `jdoe@example.edu` and import that row
     again.
   - **Use `jane.doe@partner.example`:** make it her primary (2.3; it must be verified), then import the row again.
3. If the address belongs to someone else (for example an assistant entered it as their own backup), do not import
   the row. Sort it out with the people involved; moving an address between members is done by hand in **Emails**.

### Good practice

- Start an update from an **Export Excel** file, so the names and addresses match what is stored.
- Delete the columns and rows you do not mean to change.
- Try a sheet of two or three rows first, and read every message and note.
- Leave **Default Password** empty.
- If your team uses **Member Sheet Sync**, run **Sync ALL members to Google Sheet** after an import that created
  members: new members are not copied automatically.
- Delete the spreadsheet when you are done.

## 2.6 Coming soon: review before import

> **Coming soon.** A new import flow is being built (it is not live yet, and details may change). Nothing is
> written until you have reviewed every row and confirmed.

The import will take four steps: **Upload → Review → Confirm → Result**.

1. **Upload** the sheet (`.xlsx`, up to 2,000 rows) and choose what to do with rows that match an existing member:
   **Update them** or **Skip them**. The import warns you if the same file is already in review or was imported in
   the last 30 days.
2. **Review.** Nothing has changed yet. Every row is one of:
   - **Ready:** a new member, or an update of the member the row names, with each change listed ("Organization: A →
     B"). Applied unless you tick **Skip**.
   - **Needs a decision:** skipped unless you choose otherwise. The card shows the sheet's cells, every member and
     address involved (with their roles and flags), why the row needs a decision, and exactly what each choice
     would change. Each group of similar rows has an "apply to all" control that offers only choices that are safe
     in bulk.
   - **Cannot import:** fix the sheet and upload it again.
3. **Confirm:** the counts, and every risky change spelled out. Type `import` to apply.
4. **Result:** one line per row with what changed and a link to the member. Each member's **History** records the
   import.

Decisions you may be asked for:

| Situation | Your choices |
|---|---|
| The address is a member's secondary or "other" address (the "Row 5" case) | Update the member and keep their addresses as they are (default); update and make this address the primary (only if it is verified; the old primary becomes secondary, nothing is deleted); or skip |
| The name in the sheet differs from the member's name | Same person (with or without updating the name), or skip |
| The address exists but belongs to no member | Create a new member with it, attach it to the member the row's other cells found, or skip |
| The same person is in several rows | Use one of the rows, skip the others |
| The address exists twice in different letter case | Choose the member, or skip |
| The Member UUID and the Primary Email point to different members, or the UUID matches nobody | Choose which one, match by email instead, or skip |
| A staff or superuser account and you are not the I2G Master | Skip |
| The row matches a member and you chose **Skip them** | Skip, or update the member |

**Risky changes** happen only if you tick them, one tick each: removing an address or phone number the sheet leaves
blank or replaces, re-subscribing an address (only with the person's consent), marking one unverified,
activating or deactivating a member, and staff status (I2G Master only). A tick is unavailable for the address the
row was matched on and for a member's last verified way to sign in.

Also new:

- Sheets made with **Export Excel** are matched by their **Member UUID** first, so you can change any field,
  including which address is the primary.
- The apply is all or nothing. If a member changed after your review, nothing is written and those rows return to
  the review, marked "Changed since you reviewed it".
- Only the person who uploaded an import, or the I2G Master, can change or apply it.
- **Members → Member Imports** keeps a read-only history. An import that is never applied is deleted after 24
  hours. An applied import keeps the sheet's values for 30 days and its record (who chose what) for a year.

## 2.7 Troubleshooting

| Problem | Cause and fix |
|---|---|
| "Please upload an .xlsx file" | The file is an old `.xls` workbook. Open it and save it as `.xlsx`. |
| "File size cannot exceed 5MB" | Split the sheet into smaller files. |
| "Excel file must contain a 'Primary Email' column" | The file was saved with another tab open (for example Instructions). Open the members tab, save, upload again. |
| Everything was skipped with "already exists" | **Update Existing Members** was not ticked. |
| A member says they cannot sign in with their address | Check on their member page that the address is **Verified** and the member is **Active**. Only mark it verified if you are sure it is theirs. |
| A member's name changed after an import | A filled name cell replaces the stored name when a row matches by primary email. Correct it on the member page; check the sheet before importing it again. |
| You need to undo an import | There is no undo. Each member's **History** shows what the admin changed; fix members by hand or import corrected values. |
