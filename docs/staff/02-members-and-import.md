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
- **Account:** **Account active**, and **Unfinished sign-up** (read-only: someone started a self-service sign-up
  and never finished it).
- **Permissions** (folded): the staff flag and the sections a staff account may use. Only the I2G Master can
  change them.
- **Contact Emails:** every email address of the member, each with its **Email Type**, **Verified (sign-in)** and
  **Subscribed (newsletters)**, and a **Primary email** column: **Make primary…** on a verified address,
  **Verify first** on an unverified one. The **?** next to a column title explains it.
- **Contact Phones:** phone numbers (US only), each with **Verified** and **Subscribed**.
- **Switch primary email** (at the top, next to **History**): makes another verified address the primary (2.3).
- **History** (top right): the changes saved on this page, with who made them and when, and every switch of the
  primary email made in the admin (a switch the member makes on their own account page is not recorded). Actions
  run from a list (for example **Deactivate selected members**) and the spreadsheet import are not recorded there;
  **Make selected email primary** is the exception.

### Email addresses: role, verified, subscribed

| | What it means | Where it matters |
|---|---|---|
| **Primary** | The member's main address. (A member who signed up with a phone number may have no email address at all.) | Campaigns with **Send to: Primary email only**; a new event registration copies the primary address at the time of registering. |
| **Secondary** | A backup address, often added during event registration or on the account page. When another address becomes the primary, the old primary becomes the secondary. | Campaigns with **Send to: All emails**; sign-in if verified. |
| **Other** | Any further address, for example a former secondary moved aside when a new primary was set. | As secondary, except that event registration forms offer only the primary and the secondary. |
| **Verified** | The person entered a code sent to that address, or staff marked it verified. | Only a verified address can be used to sign in with an emailed code or a password, and only a verified address can become primary. A staff member's admin sign-in codes go to their verified primary only. **Unticking it stops sign-in with that address, not mail.** |
| **Subscribed** | This address receives newsletters (**All subscribers** campaigns). | Set per address. Turning off one address leaves the others as they are. The unsubscribe link in a newsletter turns off every address of that member. Only **All subscribers** reads it: **All active members**, **Staff Members**, **Selected Members** and the event audiences mail the address whatever it says. Sign-in codes and other account mail are never affected. |

An address can belong to one member only. An address can also exist with no member at all (an **unlinked
contact**), for example one entered by hand or left over from old data.

### Account active is not an address flag

**Account active** belongs to the account, not to an address. Verified and Subscribed belong to each address (and
each phone number). None of them changes another:

| Flag | Belongs to | What it does | What it does not do |
|---|---|---|---|
| **Account active** | The member | The member can sign in at all, and is included in **All subscribers**, **All active members** and **Staff Members**. | Changes no address or phone number. It is not the tool for a bounced address (see "A bounced address" in 2.3). |
| **Verified** | One address or phone number | That address or number can be used to sign in. | Stops no mail. |
| **Subscribed** | One address (or phone number, for SMS) | Newsletters: the **All subscribers** audience. | The other audiences ignore it, and sign-in codes are never affected. |

- Unticking **Account active** leaves every address verified and subscribed: the member can no longer sign in and
  leaves the member audiences above, nothing else.
- Unticking **Verified** on a member's last verified address or phone number is allowed, but the member then cannot
  sign in with a code or a password: only a personal sign-in link from an email they already received still works,
  until it expires. Without one they cannot reach their account page to verify an address either. The admin warns
  you, on the confirmation page and again after saving: "… now has no verified email address or phone number, so
  they cannot sign in with a code or a password until one is verified". If that was a mistake, tick **Verified**
  again on an email address that is theirs, or verify their phone with **Verify by SMS code** (2.1).
- The Members list shows **Account active** as a column. The Emails list shows the **Account active** of each
  address's member next to the address's own **Verified** and **Subscribed** (empty for an unlinked contact).

**Phone numbers work differently:** a code texted to *any* number saved on a member signs in to that member's
account, whether or not the number is ticked **Verified** (it becomes verified when used). Whoever has that phone
can sign in, so add a phone number to a member only when you are sure it is theirs.

> **Coming soon** (pull requests #732 and #735, not live yet; details may change). Only a **verified** number signs
> in. For a number that is saved on an account but not verified, the sign-in page answers as if a code had been sent
> (so it never reveals which numbers have an account), and no text is sent. A number becomes verified only with a
> code:
>
> - **The member** verifies it on their account page: **Account → Phone Numbers → Verify**. An unverified number
>   there says "Verify this number to use it to sign in with a texted code".
> - **Staff** use **Verify by SMS code**, the link next to an unverified number on the member page and on the
>   phone's own page, for a member who cannot sign in another way (for example a phone-only member whose only
>   number is unverified). Talk to the member (in person, or on a call to them at a contact you already trust),
>   click **Send code to …**, ask them to read the code to you, and enter it. The code works for 10 minutes and
>   allows 5 tries, and both steps are recorded in the admin history. A staff or superuser account's number needs
>   the I2G Master.
> - **Verified** can no longer be ticked by hand, and **Mark selected phones as verified** is gone. Unticking it
>   (or **Mark selected phones as unverified (stops SMS sign-in)**) still works. A phone added in the admin starts
>   unverified, and changing a number's digits, or moving it to another member (#735), makes it unverified again.
>   Until it is verified again it can't be used to sign in, and Broadcast SMS and ticket texts skip it as one of the
>   member's numbers: use **Verify by SMS code**. The confirmation and the history list the change as **Verified**.
> - Phone rows show **Verified · SMS sign-in on** or **Unverified · no SMS sign-in**, and the Members list adds
>   "(unverified)" to an unverified number in its **Primary Phone** column.

## 2.2 Find a member

1. Go to **Members & Authentication → Members**.
2. Type in the search box and press Enter. It searches every email address of every member (primary, secondary and
   other), names, organization, title and the Member UUID, and phone numbers when you type a number on its own.
3. Narrow the list with the filters:
   - **Account active:** **Yes**, **No**, or **Unfinished sign-up** (also inactive).
   - **Primary email:** **Verified**, **Unverified** (the member cannot sign in with it), or **No primary email**.
   - **Unverified emails:** members with at least one unverified address, or none.
   - **Newsletter (All subscribers):** **Subscribed at the primary**, **Subscribed at another address only** (reached
     only by campaigns sent to all emails), or **Not subscribed at any address**. This reads the addresses only: the
     audience also leaves out inactive accounts, so add **Account active: Yes** to see who it reaches.
   - **Phone:** **Verified (SMS sign-in)**, **Unverified only**, or **No phone**.
   - **Staff status** and **Date joined**.

   Filters combine: for example **Account active: Yes** and **Primary email: Unverified** lists active members who
   cannot sign in with their main address.

What you can type:

| You type | You get |
|---|---|
| A whole address, such as `jdoe@example.edu` | The member with exactly that address first, in any letter case. Members whose address only contains it (`xjdoe@example.edu`) follow. |
| The part before the @, such as `jdoe` | The member whose address is `jdoe@…` first, then other addresses containing it (`jdoe2@…`, `ajdoe@…`). |
| Several words, such as `Jane Doe` | Members matching every word, for example the first and the last name. |
| A phone number on its own, written any way: `2095550100`, `(209) 555-0100`, `209.555.0100`, `+1 209 555 0100` | The member with that number first. Part of a number works too (`555-0100`, or an area code such as `209`), as long as it has at least 3 digits. |

- A number is searched only when the box holds nothing else. `Jane 209` finds members matching both words in their
  names, addresses and other details, not in their phone numbers. To search by phone, type the number alone.
- Clicking a column title sorts the results by that column instead of best match first.
- The **Member** pickers on other pages search the same way and list the best match first: on a contact email, a
  phone number or an event registration, start typing an address, a name or a number.

To find an address that may belong to nobody, use **Members & Authentication → Emails & Phones → Emails** and search
for it. The exact address comes first there too, and an unlinked contact has an empty member column. The filters
there are **Verified (sign-in)** (**Verified**, **Unverified emails**, **Unverified primary emails**),
**Subscribed (newsletters)**, **Email Type** and **Member account** (**Account active**, **Account inactive**,
**Staff or I2G Master**, **No member (unlinked)**). **Emails & Phones → Phones** finds a number in any of the formats
above, and has the **Member account** filter too.

## 2.3 Change a member

Edit the fields, then **Save**. The admin shows a table of what will change and asks you to type a confirmation
word. Check the table, type the word, and confirm. Actions run from a list (tick rows, choose the action, **Run**)
ask for a confirmation word the same way.

| Task | How |
|---|---|
| Fix a name, title or organization | Edit the field on the member page and save. |
| Add an address | Add a row under **Contact Emails**, set its **Email Type** to **Secondary** (or **Other** if the member already has a secondary) and save: a new row starts as **Primary**, which the page refuses. Leave **Verified** unticked: the member verifies the address from their account page. |
| Make another address the primary | On the member page, click **Switch primary email** at the top, or **Make primary…** on that address's row. See "Switch the primary email" below. (**Emails & Phones → Emails** → **Make selected email primary** does the same, and is recorded in History too.) |
| Correct a mistyped primary address | The primary's own address cannot be edited in place: its **Verified** would carry over to an address nobody proved. Add the right address as **Secondary**, have it verified, then **Switch primary email**. The old address stays as the secondary; delete it afterwards if it is useless. |
| Unsubscribe one address | Untick **Subscribed** on that address and save. (**Toggle subscription status** on the Emails list flips every selected address, so it also re-subscribes any that were off: select only subscribed ones.) Re-subscribe an address only when the person asked for it. |
| Mark an address verified | **Emails & Phones → Emails** → **Mark selected emails as verified**. Do this only when you are sure the address belongs to this person: a verified address can sign in to their account. |
| Unverify an address | Untick **Verified (sign-in)** and save, or **Mark selected emails as unverified (stops sign-in with them, not mail)** on the Emails list. It stops sign-in with that address and nothing else. The admin warns you when it was the member's last verified address or phone number (2.1). |
| Stop someone from signing in | **Members**, tick the member, action **Deactivate selected members** (or untick **Account active** on the member page). Undo with **Activate selected members**. |
| Remove a member | Deactivate instead. Deleting a member is permanent and also deletes their event registrations and check-ins. |

On a staff or superuser account other than your own, only the I2G Master can change **Account active**, the
contact addresses and phone numbers, and the primary email: the member page shows them read-only (without **Switch
primary email**), and list actions skip such accounts with "… only an I2G Master may change those".

An address that belongs to no member (an **unlinked contact**) can be linked to a member, changed or deleted only by
the I2G Master.

Changing a member's primary address does not change event registrations they made earlier: those keep the address
they were made with.

### Switch the primary email

**Needs:** the Members section; on a staff or superuser account, the I2G Master (or that account's own holder).

1. Open the member and click **Switch primary email** at the top (next to **History**), or **Make primary…** on the
   row of the address you want. **Verify first** on a row means that address is not verified and cannot become the
   primary.
2. The page that opens changes nothing yet. It lists the member's addresses with their type now and **After the
   switch**, then what the switch means for signing in and for campaigns. With several verified addresses, pick one
   first.
3. Read the warnings, type `switch` and click **Switch primary email**. You are back on the member page with a
   message saying what changed.

What happens:

- The chosen address becomes the primary, the old primary becomes the **secondary**, and the old secondary becomes
  **other**. Nothing is deleted, **no address is verified, unverified, subscribed or unsubscribed**, and nothing is
  sent to anyone.
- **Signing in:** emailed codes and passwords work with every verified address of the member, whatever its type, so
  both addresses keep working. A staff member's **admin sign-in codes** go to the verified primary only: after the
  switch they go to the new primary, and the old one no longer receives them. Codes to change the password or to
  delete the account go to the new primary too. A forgotten-password code goes to whichever verified address or
  phone number the member types, the old primary included.
- **Campaigns:** a campaign sent to the **primary email only** now goes to the new primary: **All subscribers** only
  if the new primary is subscribed; **All active members**, **Staff Members** and **Selected Members** whatever it
  says. The page warns when the switch changes who gets **All subscribers** campaigns: the new primary is
  unsubscribed while the old one was subscribed (the member stops getting those newsletters), or the other way round
  (they start getting them). Change **Subscribed** yourself only if the member asked for it. Campaigns sent to all of
  a member's addresses are not affected.
- The member's profile, the Members list, exports and the member sheet show the new primary. Event registrations
  keep the address they were made with.
- **History:** the member's History says "Primary email switched from … to …", and each address whose type changed
  has a line in its own History.
- **Undo:** switch back; the old primary stays verified as the secondary. If the switch moved the old secondary to
  **other**, switching back does not move it back (the address you switched to becomes the secondary instead): swap
  their **Email Type** on the member page if needed. Event registration forms offer only the primary and the
  secondary.

If someone changed the member's addresses while the page was open, nothing is switched: the page says so and shows
the current addresses. Confirm again.

### A bounced address: what to do

A bounce report never changes a member by itself (chapter 3). When an address bounces:

| You want to | Use | What it does |
|---|---|---|
| Stop campaigns to that one address | **Email Monitoring → Bounced addresses → Mark undeliverable** | Every campaign skips the address. Sign-in codes, tickets and notifications still reach it, the account stays active, and the member's other addresses still get campaigns. Undo with **Clear suppression**. |
| Stop only newsletters to it | Untick **Subscribed** on the address (or **Unsubscribe this address** in Bounced addresses) | Only **All subscribers** skips it; other audiences still mail it. |
| Use another of the member's addresses as their main one | **Switch primary email** here (or **Use another address as primary** in Bounced addresses) | As above; switching alone does not stop campaigns sent to all emails from mailing the bad address, so mark it undeliverable too. |
| Replace it with a new address | **Replace email** in Bounced addresses | Adds the new address and marks the old one undeliverable (or deletes it). |

- **Do not deactivate the account** because one address bounces. **Account active** is for people who should no
  longer sign in at all: it removes them from the member audiences and stops their sign-in, even with their other,
  working addresses.
- **Do not untick Verified to stop mail:** it stops no mail. Untick it only when the address must no longer sign in,
  for example when its domain no longer exists or the provider gives old usernames to new people (someone else could
  then receive sign-in codes). The admin warns you if it was the member's last verified address or phone number.

## 2.4 Export members

- **Members → Export Excel** downloads **all** members: the search box and the filters do not apply to it.
- To export some members only, tick them and choose **Export selected members to Excel** (or **… as vCard**).

The file has these columns: Member UUID, First Name, Last Name, Middle Name, Title, Organization, Active, Staff, When
Started, Primary Email, Primary Verified, Primary Subscribed, Secondary Email, Secondary Verified, Secondary
Subscribed, Phone Number, Phone Subscribed, Phone Verified.

- It shows one secondary address and one phone number per member. A member with more has the others only in the
  admin.
- A cell that starts with `=`, `+`, `-` or `@` gets a leading apostrophe so spreadsheet programs do not treat it as
  a formula.
- **The file contains personal data.** Keep it in a restricted folder, do not email it around, and delete it when
  you are done.

## 2.5 Import members

The import adds new members from a spreadsheet and, if you ask it to, updates existing members.

> **Check which version is live first.** This section describes the safe import (pull request #726). Open the
> **Import Members from Excel** page:
>
> - A **Start Import** button, and the instructions box says "Updates never delete anything": the safe import is
>   live. Follow this section.
> - A **Start Import** button, and the box does **not** say that: the **older import** is still live. With
>   **Update Existing Members** ticked it *deletes* secondary addresses and phone numbers whose cells are blank,
>   *replaces* a member's secondary address and phone number with the ones in the sheet, re-subscribes addresses,
>   un-verifies an address whose Verified cell holds FALSE (or any text other than TRUE, Yes, Y or 1), and changes
>   **Active**. Until the safe import is live, leave **Update Existing Members** unticked (rows for existing members
>   are then skipped). If you must update members, keep only the **Primary Email** column and the **First Name**,
>   **Last Name**, **Middle Name**, **Title** or **Organization** columns you are changing. The older import also
>   copies the **Phone Verified** cell onto the numbers it saves, for new members too: delete that column before
>   any import while the older import is live.
> - A **Review import** button and the steps Upload → Review → Confirm → Result: the review flow is live (2.6).

### Steps

1. Go to **Members & Authentication → Members** and click **Import Excel**.
2. Optional: click **Download Import Template** for a sheet with the right column names, an Instructions tab and
   one made-up example member in row 2 (John Doe). **Overwrite or delete that example row**, or it is imported as a
   member. A sheet made with **Export Excel** works too.
3. Fill in one person per row. The first row holds the column names, so the first person is **row 2**.
4. **Excel File:** choose the file. It must be `.xlsx` (save older `.xls` files as `.xlsx` first) and at most 5 MB.
   Save the file with the members tab open: the import reads the tab that was open when the file was saved.
5. **Default Password:** leave it empty. New members then get a random password. A shared default password would
   let anyone who knows a member's address sign in as them.

   A new member can sign in with an emailed code only once their primary address is **verified**, and **Primary
   Verified** is FALSE unless the sheet says TRUE. An unverified member cannot sign up again with that address
   either. Put TRUE only for addresses you are sure belong to that person (for example ones they gave you
   themselves), or mark the address verified later (2.3).
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
| Primary Verified | Default FALSE. TRUE makes the address a way to sign in, so use it only for addresses you are sure of. | TRUE marks the primary verified. FALSE never un-verifies it (a note says so). |
| Primary Subscribed | Default TRUE. | FALSE unsubscribes the primary. TRUE never re-subscribes it (a note says so). |
| Secondary Email | Added as the secondary address. | Added as the secondary; the previous secondary becomes "other". It starts unverified, and it is subscribed only if the member is subscribed at another address. |
| Secondary Verified, Secondary Subscribed | Used for the new secondary. | Not applied to an address the member already has (a note says so). |
| Phone Number | Added, unverified (10 digits, or +1 and 10 digits; the import does not check that the number is real). | Added next to the member's numbers, unverified. It never replaces a number. Either way, whoever has that phone can sign in with a texted code (2.1): include numbers only if they came from the members themselves. Once pull request #732 ships, only a verified number signs in: an imported number then waits until the member verifies it with a code. |
| Phone Subscribed | Used for the new number (default FALSE). | Not applied to a number the member already has (a note says so). |
| Phone Verified | **Ignored**: the number is saved unverified, whatever the cell says. | **Ignored**: a number the member already has keeps its status (verified stays verified, unverified stays unverified). |
| Active | Default TRUE. | Ignored. Use the **Activate** / **Deactivate** actions on the member list. |
| Staff | Ignored: an import never creates a staff account. | Applied only when the I2G Master imports. |
| Member UUID | Ignored by today's import. | Ignored (the coming review step uses it, see 2.6). |
| Last Updated, Primary Expired, Secondary Expired, Secondary Bounced | Accepted, not stored. | Same. |

**Phone Verified is ignored.** An import never verifies or un-verifies a phone number, and nobody can override that,
not even the I2G Master: a verified number is a way to sign in, so it must be proved with the member's own code (2.1).
Every number an import adds is saved unverified, and a number already stored keeps its status. A sheet may still have
the column (every **Export Excel** file does): the import accepts it, ignores it, and says so once, at the top of the
notes.

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
- Verify or un-verify a phone number (the **Phone Verified** column is ignored).
- Activate or deactivate an existing member, or change staff status (unless the I2G Master imports).
- Send an email or a text message.

### Rows that were not imported

| Message (start) | What it means | What to do |
|---|---|---|
| "no member has … as their primary email: it is the **secondary** (or **other**) email of …" (with **Update Existing Members** ticked), or "… already exists: it is the **secondary** (or **other**) email of …" (without it) | The address belongs to a member, but it is not their primary. This is the "Row 5" case below. | Use the member's primary address in the Primary Email cell, or make this address their primary first with **Switch primary email** on the member page (2.3; it must be verified). Then import that row again with **Update Existing Members** ticked. |
| "… it is a contact email that is not linked to any member" | The address exists with no member. | Ask the I2G Master to link it to the right member or delete it (only the I2G Master can change an unlinked contact), then import again. |
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

A sheet with a **Phone Verified** column gets one more note, about the file rather than a row, at the top of the
list: "Phone Verified column ignored: an import never verifies or un-verifies a phone number. …".

### Example: "Row 5"

Row numbers are spreadsheet rows: the column names are row 1, so row 5 is the fourth person. Suppose row 5 of the
sheet is Jane Doe with `jane.doe@partner.example` in **Primary Email**, and **Update Existing Members** is ticked. The
result says:

> Row 5: no member has jane.doe@partner.example as their primary email: it is the secondary email of Jane Doe
> (member 1b2c3d4e-…), whose primary email is jdoe@example.com. Row not imported. Rows are matched to existing
> members by primary email only: put the member's primary email in the Primary Email cell, or make this address
> their primary email on the member page first

Nothing about Jane changed. To finish:

1. Click **Open member** and check that this is the same Jane Doe.
2. Decide which address should be her primary:
   - **Keep `jdoe@example.com`:** change the Primary Email cell of row 5 to `jdoe@example.com` and import that row
     again.
   - **Use `jane.doe@partner.example`:** make it her primary with **Switch primary email** on her member page
     (2.3; it must be verified), then import the row again.
3. If **Open member** shows somebody else (for example an assistant who saved Jane's address as their own backup),
   do not import the row. Sort it out with the people involved. Moving an address to another member is done by hand
   in **Emails**: a primary address cannot be moved, and a moved address keeps its **Verified** tick, which lets its
   new owner sign in with it, so untick it unless you are sure.

### Good practice

- Start an update from an **Export Excel** file, so the names and addresses match what is stored.
- Delete the columns and rows you do not mean to change.
- Try a sheet of two or three rows first, and read every message and note.
- Leave **Default Password** empty.
- If your team uses **Member Sheet Sync**: members an import creates are not copied to the sheet until the next
  sync. To copy them at once, tick any member, choose **Sync ALL members to Google Sheet** and **Run** (it copies
  every member).
- Take an **Export Excel** before a large update: the import cannot be undone (2.7).
- Delete the spreadsheets when you are done.

## 2.6 Coming soon: review before import

> **Coming soon.** A new import flow is being built (it is not live yet, and details may change). Nothing is
> written until you confirm.

The import will take four steps: **Upload → Review → Confirm → Result**.

1. **Upload** the sheet (`.xlsx`, up to 2,000 rows) and choose what to do with rows that match an existing member:
   **Update them** or **Skip them**. If the same file is already in review or was imported in the last 30 days, the
   page says so, and you must tick **This file was uploaded before; review it again anyway** to go on.
2. **Review.** Nothing has changed yet. Every row is one of:
   - **Ready:** a new member, or an update of the member the row names, with each change listed ("Organization:
     'A' → 'B'"). Applied unless you tick **Skip**.
   - **No change:** the row matches a member and would change nothing.
   - **Needs a decision:** every such row starts on **Skip this row**. The card shows the sheet's cells, every
     member and address involved (with their roles and flags), why the row needs a decision, and the choices; the
     one the import suggests is marked. It spells out what the chosen option will change (save another choice to
     see its plan). Each group of similar rows has an "apply to all" control that offers only choices that are safe
     in bulk.
   - **Cannot import:** fix the sheet and upload it again.
3. **Confirm:** the counts, and every risky change spelled out. Type `import` to apply.
4. **Result:** one line per row with what changed and a link to the member. The **History** of each member the
   import created or updated records it.

Decisions you may be asked for (each starts on **Skip**):

| Situation | Your choices |
|---|---|
| The address is a member's secondary or "other" address (the "Row 5" case) | Update the member and keep their addresses as they are (the suggested choice); update and make this address the primary (only if it is verified; the old primary becomes secondary, nothing is deleted); or skip |
| The name in the sheet differs from the member's name | Same person (with or without updating the name), or skip |
| The address exists but belongs to no member | Create a new member with it, attach it to the member the row's other cells found, or skip |
| The same person is in several rows | Use one of the rows, skip the others |
| The address exists twice in different letter case | Choose the member, or skip |
| The Member UUID and the Primary Email point to different members, or the UUID matches nobody | Choose which one, match by email instead, or skip |
| A staff or superuser account and you are not the I2G Master | Skip |
| The row matches a member and you chose **Skip them** | Skip, or update the member |

**Risky changes** happen only if you tick them: removing an address or phone number the sheet leaves blank or
replaces, re-subscribing an address or number (only with the person's consent), marking an email address verified
(it then becomes a way to sign in) or unverified, activating or deactivating a member, and staff status (I2G Master
only). There is no tick to verify or un-verify a phone number: the review ignores **Phone Verified** as in 2.5, lists
the column under "Not imported", and says so on the Review, Confirm and Result pages. Each row has its own ticks, and
a **Tick all** button ticks every row of one kind at once: use it with care. A removal is unavailable for the address
the row was matched on and for a member's only verified way to sign in. On a staff or superuser account only the I2G
Master can tick them, and an unfinished sign-up can be neither activated nor verified by an import.

Also new:

- Sheets made with **Export Excel** are matched by their **Member UUID** first, so a row still finds its member
  after you change the Primary Email cell. An address that is not already one of the member's is not added (a note
  says so), and making another of their addresses the primary is a decision you confirm (it must be verified).
- The apply is all or nothing. If a member changed after your review, nothing is written and those rows return to
  the review on **Skip**, marked "Changed since you reviewed it".
- Only the person who uploaded an import, or the I2G Master, can change or apply it, and an import never does more
  than its uploader's own access allows.
- **Members → Member Imports** keeps a read-only history. An import that is never applied is deleted after 24
  hours. An applied import keeps the sheet's values for 30 days and its record (who chose what) for a year.

## 2.7 Troubleshooting

| Problem | Cause and fix |
|---|---|
| "Please upload an .xlsx file" | The file is an old `.xls` workbook. Open it and save it as `.xlsx`. |
| "File size cannot exceed 5MB" | Split the sheet into smaller files. |
| "Excel file must contain a 'Primary Email' column" | The file was saved with another tab open (for example Instructions), or row 1 does not hold the column names. Open the members tab, check row 1, save, upload again. |
| Everything was skipped with "… already exists: … Skipped because "Update Existing Members" is off" | **Update Existing Members** was not ticked. (Rows that say "… already exists: it is the secondary email of …" are the "Row 5" case instead.) |
| A member says they cannot sign in with their address | Check on their member page that the address is **Verified** and **Account active** is ticked. Only mark it verified if you are sure it is theirs. **Primary email: Unverified** on the Members list finds members in this state. |
| "The current primary email's address and type cannot be edited directly" | The primary is changed with **Switch primary email** (2.3), never by editing the row. To correct its address, add the right one as a secondary, have it verified, then switch. |
| **Switch primary email** says the member has no other verified address | Add the new address as **Secondary**, let the member verify it from their account page (or tick **Verified** if you are sure it is theirs), then switch. |
| "… now has no verified email address or phone number" after a save | You unticked (or removed) their last verified address or phone number: they cannot sign in with a code or a password. If that was a mistake, tick **Verified** again on an email address that is theirs, or verify their phone with **Verify by SMS code**. |
| A member cannot sign in with their phone | Check on their member page that the number is right and **Account active** is ticked. Once pull request #732 ships, the number must also be verified (an unverified number gets no text): they verify it on their account page, or you use **Verify by SMS code** with them (2.1). The safe import (2.5) never verifies a number, whatever the sheet's **Phone Verified** said. |
| A member's name changed after an import | A filled name cell replaces the stored name when a row matches by primary email. Correct it on the member page; check the sheet before importing it again. |
| You need to undo an import | There is no undo, and this import leaves nothing in a member's **History**. Compare with the **Export Excel** you took before (see Good practice) and fix members by hand. Importing again cannot remove what an import added or verified. |
