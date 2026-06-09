import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type * as SessionStore from '../sessionStore';

const SESSION_KEY = 'itg-assistant-session';
const TRANSCRIPT_KEY = 'itg-assistant-transcript';

// Monotonic across the whole file so freshly minted ids are always unique.
let uuidCounter = 0;

// Re-imported fresh in beforeEach so the module's in-memory fallback state
// can never leak between tests.
let store: typeof SessionStore;

describe('sessionStore', () => {
  beforeEach(async () => {
    sessionStorage.clear();
    // jsdom may lack crypto.randomUUID; provide a deterministic stub.
    vi.stubGlobal('crypto', {randomUUID: () => `uuid-${++uuidCounter}`});
    vi.resetModules();
    store = await import('../sessionStore');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  describe('getSessionId', () => {
    it('mints and persists an id on first call', () => {
      expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
      const id = store.getSessionId();
      expect(id).toMatch(/^uuid-\d+$/);
      expect(sessionStorage.getItem(SESSION_KEY)).toBe(id);
    });

    it('reuses the existing id on subsequent calls', () => {
      const first = store.getSessionId();
      const second = store.getSessionId();
      expect(second).toBe(first);
    });

    it('falls back to an in-memory id when sessionStorage throws', () => {
      // Replace sessionStorage with one whose accessors throw (privacy mode).
      const throwing = {
        getItem: () => {
          throw new Error('denied');
        },
        setItem: () => {
          throw new Error('denied');
        },
        removeItem: () => {
          throw new Error('denied');
        },
      };
      vi.stubGlobal('sessionStorage', throwing);

      const id = store.getSessionId();
      expect(id).toMatch(/^uuid-\d+$/);
      // Stable within the tab even though storage is unavailable.
      expect(store.getSessionId()).toBe(id);
    });

    it('mints a fallback id when crypto.randomUUID is unavailable', () => {
      // Drop the Web Crypto UUID API to exercise the non-crypto fallback.
      vi.stubGlobal('crypto', {});
      const id = store.getSessionId();
      expect(id).toMatch(/^s-\d+-/);
    });
  });

  describe('clearConversation', () => {
    it('mints a new id and clears the transcript', () => {
      const original = store.getSessionId();
      store.saveTranscript([{id: 'm1', role: 'user', content: 'hi'}]);

      store.clearConversation();

      expect(sessionStorage.getItem(TRANSCRIPT_KEY)).toBeNull();
      const fresh = store.getSessionId();
      expect(fresh).not.toBe(original);
      expect(store.loadTranscript()).toEqual([]);
    });

    it('rotates the in-memory id when sessionStorage throws', () => {
      vi.stubGlobal('sessionStorage', {
        getItem: () => {
          throw new Error('denied');
        },
        setItem: () => {
          throw new Error('denied');
        },
        removeItem: () => {
          throw new Error('denied');
        },
      });

      // Seed the in-memory id, then clear; the id must change.
      const before = store.getSessionId();
      store.clearConversation();
      const after = store.getSessionId();
      expect(after).not.toBe(before);
    });

    it('never resurrects the old id when only the storage write fails', () => {
      const original = store.getSessionId();

      // Quota-style partial failure: reads and removes succeed, writes throw.
      const real = sessionStorage;
      vi.stubGlobal('sessionStorage', {
        getItem: real.getItem.bind(real),
        removeItem: real.removeItem.bind(real),
        setItem: () => {
          throw new Error('quota');
        },
      });

      store.clearConversation();

      // The old id was dropped from storage and the rotated id is served.
      expect(real.getItem(SESSION_KEY)).toBeNull();
      expect(store.getSessionId()).not.toBe(original);
    });
  });

  describe('transcript persistence', () => {
    it('round-trips a saved transcript', () => {
      const messages = [
        {id: 'm1', role: 'user' as const, content: 'q'},
        {id: 'm2', role: 'assistant' as const, content: 'a'},
      ];
      store.saveTranscript(messages);
      expect(store.loadTranscript()).toEqual(messages);
    });

    it('returns [] when nothing is stored', () => {
      expect(store.loadTranscript()).toEqual([]);
    });

    it('caps persistence to the last 50 messages', () => {
      const messages = Array.from({length: 60}, (_, i) => ({
        id: `m${i}`,
        role: 'user' as const,
        content: `c${i}`,
      }));
      store.saveTranscript(messages);
      const loaded = store.loadTranscript();
      expect(loaded).toHaveLength(50);
      // The most recent messages are kept (oldest 10 dropped).
      expect(loaded[0].id).toBe('m10');
      expect(loaded[49].id).toBe('m59');
    });

    it('tolerates non-JSON garbage in storage', () => {
      sessionStorage.setItem(TRANSCRIPT_KEY, 'not json{');
      expect(store.loadTranscript()).toEqual([]);
    });

    it('tolerates a non-array JSON payload', () => {
      sessionStorage.setItem(TRANSCRIPT_KEY, JSON.stringify({nope: true}));
      expect(store.loadTranscript()).toEqual([]);
    });

    it('drops malformed entries while keeping valid ones', () => {
      sessionStorage.setItem(
        TRANSCRIPT_KEY,
        JSON.stringify([
          {id: 'ok', role: 'user', content: 'good'},
          {id: 'bad-role', role: 'system', content: 'x'},
          {id: 42, role: 'user', content: 'non-string id'},
          {role: 'user', content: 'missing id'},
          'just a string',
        ]),
      );
      expect(store.loadTranscript()).toEqual([{id: 'ok', role: 'user', content: 'good'}]);
    });
  });
});
