# Member import review

How Members → Import stages a sheet for review and applies it. Operator how-to:
[Member import/export](../cms-admin/operations.md#member-importexport).

## Flow

```
Upload ──▶ Review ◀──▶ Confirm ──▶ Result
parse +     choices      type          one transaction,
analyse     saved per    "import"      all or nothing
(no writes) row
```

| Step | URL (`admin:` name) | Code |
|---|---|---|
| Upload | `authn/member/import-excel/` (`authn_member_import_excel`) | `admin/members/import_views.upload_view` → `reader.read_upload` → `review.batches.create_batch` |
| Review | `…/<batch>/review/` (`authn_member_import_review`) | `review_view` (GET), `_save` → `batches.save_choices` (POST) |
| Confirm | `…/<batch>/confirm/` (`authn_member_import_confirm`, request limit `staff-bulk`) | `confirm_view` → `review.apply.apply_batch` |
| Result | `…/<batch>/` (`authn_member_import_result`) | `result_view` |
| Discard | `…/<batch>/discard/` (POST) | `batches.discard_batch` |
| History | `authn/memberimportbatch/` | `admin/members/import_batch.py` (read-only, no export) |

Every view re-checks authn-app access (`admin_view` only checks `is_staff`). Only the uploader or an I2G Master may
save choices, apply or discard; other authn admins get the review read-only. Rights are always the **uploader's and
the actor's together** (`import_views.analysis_context`): an I2G Master applying another admin's import never lends it
master rights, so the uploader can't use the master's apply to reach staff accounts or master-only ticks. An import
whose uploader was deleted is never applied.

## Storage

`MemberImportBatch` and `MemberImportRow` (`authn/models/members/member_import.py`, migration `authn.0023`). A batch
keeps the parsed values, never the file. Each row stores:

- `values`: the parsed cells and the text as typed;
- `candidates`: the records its analysis read (its addresses, number and Member UUID, and every contact of each
  member involved), as canonical JSON (`review/lookup.row_slice`);
- `fingerprint`: SHA-256 of `candidates` without display-only fields (`created`, `date_joined`, `last_login`). Values,
  not `updated_at`, because queryset `.update()` calls don't touch `auto_now`;
- `analysis`: the conflict's facts, the options (enabled or disabled with a reason) and the default;
- `risky`: the R-items per member the row could update; `choice`, `ticks`, `chosen_by`, `chosen_at`; the `outcome`.

Both tables are in `DENIED_MODEL_LABELS` (no AI action engine or `/admin-api/` access). `review/purge.py` enforces
`settings.MEMBER_IMPORT` (24 h for unapplied batches; after 30 days every field that names a person is blanked:
values, snapshots, analysis, warnings, outcome details, last error and activity details; records kept 1 year), from the
worker's maintenance (`Member import purge`) and from each upload-page visit. The reader stops at `max_rows` member rows
and at `max_rows_read` rows read (blank ones included), so a compressed workbook can't expand without bound.

## Analysis (`services/members/import_/review/`)

| Module | Role |
|---|---|
| `lookup.py` | One snapshot of every record the sheet names, in a fixed number of queries per 500 values. Addresses compare through `UPPER()` and `upper().lower()` keys, as `login_guard` does |
| `grouping.py` | Cross-row checks: V2/V4/V7/V8 cells set aside; C1 groups (same member, or same new address) |
| `analysis.py` | Per row: Member UUID → Primary Email in any role → unlinked contact → new member; conflicts C2–C9 in precedence order; status |
| `choices.py`, `describe.py` | Options per conflict, bulk-safe choices, and the sentences shown |
| `risky.py` | R1–R9 items per target member, with the disabled reasons (R9 "mark verified": a verified address is a sign-in factor). R6/R9 cover email addresses only |
| `plan.py`, `plan_contacts.py` | What a choice writes, in order, with one line per change; `ContactState` follows the member's contacts through the plan |
| `selection.py` | Posted choices checked against the row's options (a forged POST fails); cross-row problems that block the apply |
| `apply.py`, `execute.py` | The transaction and the writes; `contacts.py` holds the guarded contact writes |
| `batches.py`, `purge.py` | Persistence of batches and choices; retention |

Every conflict starts on Skip. The suggested choice is marked; bulk controls set a choice for a whole conflict group
only where it is allowed on each row.

**Phone Verified is ignored.** A verified phone number is a sign-in factor, so only the member's own one-time code
produces one. `parsing.IGNORED_COLUMNS` makes the column informational: it is not parsed, not stored in `values`, and
listed as "Not imported". The reader puts its note in `columns["notes"]`, which the review, confirm and result pages
and the one-step result (`ImportResult.note_file`) show. A new member's number is planned and written unverified
(`plan._create_phone`, `execute.execute_creations`). A stored number gets no Verified cell (`plan_contacts.plan_phone`)
and no R6/R9 item (`risky._owned_cells`), so an R6/R9 tick for a phone is a forged POST. `contacts.set_phone_flags`
refuses any flag but `subscribe`.

## Apply

`apply_batch` locks the batch row (`select_for_update`), checks its status, expiry and `choices_version`, locks every
member the review read in primary-key order, reloads the snapshot and re-runs the analysis. A row whose fingerprint,
status or conflict differs, or whose choice or ticks are no longer allowed (a privilege change), sends the batch back to
review: those rows get the new analysis, their choice reset to Skip (not to their default) and `changed_since_review`.
The planner itself never activates or verifies an unfinished self-service sign-up, whatever the ticks say. Otherwise every row's
plan is written in row order; new members are bulk-created (one sheet sync is scheduled after commit), updates are
saved op by op so the save signals fire. `make_contact_email_primary`, `delete_contact_email` and `delete_contact_phone`
run as savepoints with their own guards; `create_contact_email` is never used, so no mail is sent. Any error rolls back
everything and is stored in `last_error`. Each affected member gets a LogEntry, and the batch one more.

`import_members_from_excel` (`excel.py`) runs the same analysis and apply without a review: ready rows only, every
conflict skipped, no ticks.

## Decisions taken

Recorded in the PR that introduced the review (stacked on the Phase 0 hotfix #726): DB batch tables, all-or-nothing
apply, make-primary for verified addresses only, new contacts on existing members start unverified, Skip preselected on
every conflict, the plan's name rule, settings-only retention, the non-interactive API kept, contacts never moved
between members, a 2,000-row cap, and ready updates applied without a per-row click. Decided on 2026-11-12 (#726):
the Phone Verified column is ignored, with no tick and no I2G Master override.
