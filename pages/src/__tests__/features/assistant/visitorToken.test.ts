import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import type * as VisitorToken from '@/features/assistant/utils/visitorToken';

const STORAGE_KEY = 'itg-assistant-visitor';

/** A localStorage whose every accessor throws (Safari private mode, blocked site data). */
const throwingStorage = {
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

// Re-imported fresh in beforeEach so the module's in-memory fallback can never
// leak between tests.
let visitor: typeof VisitorToken;

describe('visitorToken', () => {
  beforeEach(async () => {
    localStorage.clear();
    vi.resetModules();
    visitor = await import('@/features/assistant/utils/visitorToken');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('holds no token until the backend provides one', () => {
    expect(visitor.getVisitorToken()).toBeNull();
  });

  it('persists a stored token in localStorage', () => {
    visitor.storeVisitorToken('tok-1');
    expect(localStorage.getItem(STORAGE_KEY)).toBe('tok-1');
    expect(visitor.getVisitorToken()).toBe('tok-1');
  });

  it('survives a page reload (fresh module instance, same storage)', async () => {
    visitor.storeVisitorToken('tok-1');
    vi.resetModules();
    const reloaded = await import('@/features/assistant/utils/visitorToken');
    expect(reloaded.getVisitorToken()).toBe('tok-1');
  });

  it('replaces the held token when told to store a new one', () => {
    visitor.storeVisitorToken('tok-1');
    visitor.storeVisitorToken('tok-2');
    expect(visitor.getVisitorToken()).toBe('tok-2');
    expect(localStorage.getItem(STORAGE_KEY)).toBe('tok-2');
  });

  it('adopts an offered token only when none is held', () => {
    visitor.adoptVisitorToken('tok-1');
    visitor.adoptVisitorToken('tok-2');
    expect(visitor.getVisitorToken()).toBe('tok-1');
  });

  it('adopts a new offer once the held token is gone', () => {
    visitor.adoptVisitorToken('tok-1');
    localStorage.clear();
    vi.resetModules();
    return import('@/features/assistant/utils/visitorToken').then((reloaded) => {
      reloaded.adoptVisitorToken('tok-2');
      expect(reloaded.getVisitorToken()).toBe('tok-2');
    });
  });

  it.each([undefined, null, '', 42, {token: 'x'}, ['tok'], 'x'.repeat(513)])(
    'ignores a malformed value (%j) and keeps the working token',
    (value) => {
      visitor.storeVisitorToken('tok-1');
      visitor.storeVisitorToken(value);
      visitor.adoptVisitorToken(value);
      expect(visitor.getVisitorToken()).toBe('tok-1');
      expect(localStorage.getItem(STORAGE_KEY)).toBe('tok-1');
    },
  );

  it('ignores garbage already sitting in storage', () => {
    localStorage.setItem(STORAGE_KEY, 'x'.repeat(5000));
    expect(visitor.getVisitorToken()).toBeNull();
    visitor.adoptVisitorToken('tok-1');
    expect(visitor.getVisitorToken()).toBe('tok-1');
  });

  it('falls back to memory when localStorage throws on every access', () => {
    vi.stubGlobal('localStorage', throwingStorage);

    expect(visitor.getVisitorToken()).toBeNull();
    expect(() => visitor.adoptVisitorToken('tok-1')).not.toThrow();
    // Stable within the tab even though nothing could be persisted.
    expect(visitor.getVisitorToken()).toBe('tok-1');
    visitor.adoptVisitorToken('tok-2');
    expect(visitor.getVisitorToken()).toBe('tok-1');
    visitor.storeVisitorToken('tok-3');
    expect(visitor.getVisitorToken()).toBe('tok-3');
  });

  it('falls back to memory when only the write fails (quota)', () => {
    const real = localStorage;
    vi.stubGlobal('localStorage', {
      getItem: real.getItem.bind(real),
      removeItem: real.removeItem.bind(real),
      setItem: () => {
        throw new Error('quota');
      },
    });

    visitor.storeVisitorToken('tok-1');

    expect(real.getItem(STORAGE_KEY)).toBeNull();
    expect(visitor.getVisitorToken()).toBe('tok-1');
  });

  it('does not let a stale stored token shadow a replacement that could not be written', () => {
    visitor.storeVisitorToken('expired-tok');
    const real = localStorage;
    vi.stubGlobal('localStorage', {
      getItem: real.getItem.bind(real),
      removeItem: real.removeItem.bind(real),
      setItem: () => {
        throw new Error('quota');
      },
    });

    visitor.storeVisitorToken('fresh-tok');

    expect(visitor.getVisitorToken()).toBe('fresh-tok');
    expect(real.getItem(STORAGE_KEY)).toBeNull();
  });

  it('works when localStorage does not exist at all', () => {
    vi.stubGlobal('localStorage', undefined);

    expect(visitor.getVisitorToken()).toBeNull();
    visitor.storeVisitorToken('tok-1');
    expect(visitor.getVisitorToken()).toBe('tok-1');
  });
});
