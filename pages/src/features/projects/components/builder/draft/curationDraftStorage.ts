import type {ProjectGridRow} from '../../grid/contracts/projectGrid';

// The curation being built (its saved projects, name and note) is a draft until it is saved, which needs signing
// in — and the login button reloads the page. Keep the draft in localStorage so it survives that reload, closing
// the tab and coming back later; it is dropped once it is saved. The draft records whose it is: a member's draft is
// only restored for that member, so the next person on a shared computer does not get it, while a guest's draft
// carries over when the guest signs in.
const DRAFT_STORAGE_KEY = 'past-projects:builder:draft';
// Before drafts outlived the tab, the projects alone were kept in sessionStorage. Picked up once; the first write
// of the new draft removes it.
const LEGACY_MERGED_ROWS_STORAGE_KEY = 'past-projects:builder:merged-rows';

export interface CurationDraft {
  /** The member the draft belongs to; null for a guest's. */
  owner: string | null;
  rows: ProjectGridRow[];
  name: string;
  note: string;
}

const EMPTY_DRAFT: CurationDraft = {owner: null, rows: [], name: '', note: ''};

// The text fields of a stored row. Storage is outside this page's control (an older version, another tab, an
// extension, a hand edit), and the tables format these fields as strings, so one missing field would crash
// the whole page on every visit.
const ROW_TEXT_FIELDS = [
  'semester_label',
  'class_code',
  'team_number',
  'team_name',
  'project_title',
  'organization',
  'industry',
  'abstract',
  'student_names',
  'is_presenting',
] as const satisfies ReadonlyArray<keyof ProjectGridRow>;

const stringOrEmpty = (value: unknown) => (typeof value === 'string' ? value : '');

/** A stored row with every text field a string (missing ones empty); null when it is not a project row at all. */
const toDraftRow = (value: unknown): ProjectGridRow | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const stored = value as Record<string, unknown>;
  const row = Object.fromEntries(ROW_TEXT_FIELDS.map((field) => [field, stringOrEmpty(stored[field])])) as Omit<
    ProjectGridRow,
    'id'
  >;
  const id = stringOrEmpty(stored.id);
  if (!id && !row.project_title && !row.team_name) return null;
  return id ? {id, ...row} : row;
};

/** The project rows of a stored list; anything that is not one is dropped. */
const toDraftRows = (value: unknown): ProjectGridRow[] =>
  Array.isArray(value) ? value.flatMap((item) => toDraftRow(item) ?? []) : [];

const readLegacyDraft = (): CurationDraft => {
  try {
    const raw = sessionStorage.getItem(LEGACY_MERGED_ROWS_STORAGE_KEY);
    return {...EMPTY_DRAFT, rows: toDraftRows(raw ? JSON.parse(raw) : [])};
  } catch {
    return EMPTY_DRAFT;
  }
};

/** A parsed stored draft as this member's draft; empty when malformed or owned by someone else. */
const draftFor = (parsed: unknown, memberId: string | null): CurationDraft => {
  const stored = parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null;
  const owner = typeof stored?.owner === 'string' ? stored.owner : null;
  if (!stored || !Array.isArray(stored.rows) || (owner && owner !== memberId)) {
    return EMPTY_DRAFT;
  }
  return {owner, rows: toDraftRows(stored.rows), name: stringOrEmpty(stored.name), note: stringOrEmpty(stored.note)};
};

/** The stored draft, unless it belongs to another member (or is unreadable). */
export const readPersistedDraft = (memberId: string | null): CurationDraft => {
  try {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) return readLegacyDraft();
    return draftFor(JSON.parse(raw), memberId);
  } catch {
    return EMPTY_DRAFT;
  }
};

/** Store the draft; an empty one (no rows) is removed instead. */
export const writePersistedDraft = (draft: CurationDraft) => {
  try {
    sessionStorage.removeItem(LEGACY_MERGED_ROWS_STORAGE_KEY);
    if (draft.rows.length) {
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
    } else {
      localStorage.removeItem(DRAFT_STORAGE_KEY);
    }
  } catch {
    // localStorage can throw (private mode / quota / disabled) — degrade to in-memory only.
  }
};

export const clearPersistedDraft = () => {
  try {
    localStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch {
    // ignore — nothing to clean up if storage is unavailable.
  }
};

/**
 * Follow the draft that other tabs store (the `storage` event fires only in the tabs that did not write):
 * `onChange` gets each new draft, empty when one was removed. A value this page cannot read, or another
 * member's draft, is skipped. Returns the unsubscribe function.
 */
export const subscribeToOtherTabsDraft = (
  getMemberId: () => string | null,
  onChange: (draft: CurationDraft) => void,
) => {
  const handleStorage = (event: StorageEvent) => {
    if (event.key !== DRAFT_STORAGE_KEY) return;
    if (event.newValue === null) {
      onChange(EMPTY_DRAFT);
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(event.newValue);
    } catch {
      return;
    }
    const owner = (parsed as {owner?: unknown} | null)?.owner;
    if (typeof owner === 'string' && owner !== getMemberId()) return;
    onChange(draftFor(parsed, getMemberId()));
  };
  window.addEventListener('storage', handleStorage);
  return () => window.removeEventListener('storage', handleStorage);
};
