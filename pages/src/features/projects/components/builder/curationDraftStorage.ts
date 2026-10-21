import type {ProjectGridRow} from '../projectGrid';

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

const readLegacyDraft = (): CurationDraft => {
  try {
    const raw = sessionStorage.getItem(LEGACY_MERGED_ROWS_STORAGE_KEY);
    const rows = raw ? JSON.parse(raw) : [];
    return Array.isArray(rows) ? {...EMPTY_DRAFT, rows: rows as ProjectGridRow[]} : EMPTY_DRAFT;
  } catch {
    return EMPTY_DRAFT;
  }
};

const stringOrEmpty = (value: unknown) => (typeof value === 'string' ? value : '');

/** A parsed stored draft as this member's draft; empty when malformed or owned by someone else. */
const draftFor = (parsed: Partial<CurationDraft> | null, memberId: string | null): CurationDraft => {
  const owner = typeof parsed?.owner === 'string' ? parsed.owner : null;
  if (!parsed || !Array.isArray(parsed.rows) || (owner && owner !== memberId)) {
    return EMPTY_DRAFT;
  }
  return {owner, rows: parsed.rows, name: stringOrEmpty(parsed.name), note: stringOrEmpty(parsed.note)};
};

/** The stored draft, unless it belongs to another member (or is unreadable). */
export const readPersistedDraft = (memberId: string | null): CurationDraft => {
  try {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) return readLegacyDraft();
    return draftFor(JSON.parse(raw) as Partial<CurationDraft> | null, memberId);
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
