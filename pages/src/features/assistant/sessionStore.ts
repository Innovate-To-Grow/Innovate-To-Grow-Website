import type {DisplayMessage} from './components/types';

/** sessionStorage key holding the conversation's opaque session id. */
const SESSION_KEY = 'itg-assistant-session';
/** sessionStorage key holding the persisted transcript (JSON array). */
const TRANSCRIPT_KEY = 'itg-assistant-transcript';
/** Cap on persisted turns so the transcript can't grow without bound. */
const MAX_PERSISTED_MESSAGES = 50;

/**
 * In-memory fallback used when sessionStorage is unavailable (e.g. Safari
 * private mode throws on access). Keeps the session id stable within the tab.
 */
let memorySessionId: string | null = null;

/** Generate an opaque session id, tolerating environments without crypto.randomUUID. */
function mintSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback id; only reached in environments lacking the Web Crypto UUID API.
  return `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Return the current session id, minting and persisting one on first use.
 * Always returns a string; sessionStorage failures fall back to memory.
 */
export function getSessionId(): string {
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const id = mintSessionId();
    sessionStorage.setItem(SESSION_KEY, id);
    return id;
  } catch {
    // Privacy mode or disabled storage: hold the id in memory for this tab.
    if (memorySessionId === null) memorySessionId = mintSessionId();
    return memorySessionId;
  }
}

/** Narrow an unknown value to a well-formed DisplayMessage. */
function isDisplayMessage(value: unknown): value is DisplayMessage {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === 'string' &&
    (candidate.role === 'user' || candidate.role === 'assistant') &&
    typeof candidate.content === 'string'
  );
}

/**
 * Load the persisted transcript. Any malformed/garbage payload yields an empty
 * transcript rather than throwing.
 */
export function loadTranscript(): DisplayMessage[] {
  try {
    const raw = sessionStorage.getItem(TRANSCRIPT_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isDisplayMessage);
  } catch {
    return [];
  }
}

/** Persist the transcript, keeping only the most recent {@link MAX_PERSISTED_MESSAGES}. */
export function saveTranscript(messages: DisplayMessage[]): void {
  try {
    const capped = messages.slice(-MAX_PERSISTED_MESSAGES);
    sessionStorage.setItem(TRANSCRIPT_KEY, JSON.stringify(capped));
  } catch {
    /* best-effort: nothing to do if storage is unavailable */
  }
}

/**
 * Start a fresh conversation: drop the stored transcript and mint a brand-new
 * session id (so the backend treats subsequent turns as a new conversation).
 */
export function clearConversation(): void {
  const id = mintSessionId();
  try {
    sessionStorage.removeItem(TRANSCRIPT_KEY);
    sessionStorage.setItem(SESSION_KEY, id);
  } catch {
    // Partial failure (e.g. quota: removes succeed, writes fail): drop the old
    // stored id too, so a later getSessionId() can never resurrect the
    // previous session, then remember the rotated id in memory.
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* storage fully unavailable; the in-memory id below still rotates */
    }
    memorySessionId = id;
  }
}
