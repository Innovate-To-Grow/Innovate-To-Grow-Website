import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
}));

vi.mock('@/lib/api/api-client', () => ({
  api: {post: mocks.post},
}));

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const STORAGE_KEY = 'i2g_visitor_id';

// The module keeps an in-memory id for browsers without usable storage, so every test loads a fresh copy.
async function loadAnalytics() {
  vi.resetModules();
  return import('@/lib/api/analytics');
}

function sentVisitorIds(): unknown[] {
  return mocks.post.mock.calls.map(([, body]) => (body as {visitor_id?: unknown}).visitor_id);
}

describe('page-view analytics', () => {
  beforeEach(() => {
    mocks.post.mockReset();
    mocks.post.mockResolvedValue({status: 201});
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('posts the page view with a random visitor id', async () => {
    const {trackPageView, VISITOR_ID_STORAGE_KEY} = await loadAnalytics();

    await trackPageView({path: '/about', referrer: 'https://example.com/'});

    expect(VISITOR_ID_STORAGE_KEY).toBe(STORAGE_KEY);
    expect(mocks.post).toHaveBeenCalledTimes(1);
    const [url, body] = mocks.post.mock.calls[0];
    expect(url).toBe('/analytics/pageview/');
    expect(body).toEqual({path: '/about', referrer: 'https://example.com/', visitor_id: expect.stringMatching(UUID_V4)});
  });

  it('stores the id and sends the same one on every later page view', async () => {
    const {trackPageView} = await loadAnalytics();

    await trackPageView({path: '/a', referrer: ''});
    await trackPageView({path: '/b', referrer: ''});

    const [first, second] = sentVisitorIds();
    expect(first).toMatch(UUID_V4);
    expect(second).toBe(first);
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(first);
  });

  it('keeps the id across page loads', async () => {
    const firstLoad = await loadAnalytics();
    await firstLoad.trackPageView({path: '/a', referrer: ''});
    const secondLoad = await loadAnalytics();
    await secondLoad.trackPageView({path: '/b', referrer: ''});

    const [first, second] = sentVisitorIds();
    expect(second).toBe(first);
  });

  it('reuses an id that is already stored', async () => {
    const storedId = '3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f';
    window.localStorage.setItem(STORAGE_KEY, storedId);
    const {trackPageView} = await loadAnalytics();

    await trackPageView({path: '/', referrer: ''});

    expect(sentVisitorIds()).toEqual([storedId]);
  });

  it('follows the stored id when another tab replaces it', async () => {
    const {trackPageView} = await loadAnalytics();
    await trackPageView({path: '/a', referrer: ''});

    window.localStorage.setItem(STORAGE_KEY, 'written-by-another-tab');
    await trackPageView({path: '/b', referrer: ''});

    expect(sentVisitorIds()[1]).toBe('written-by-another-tab');
  });

  it('starts a new id when the stored one was cleared', async () => {
    const {trackPageView} = await loadAnalytics();
    await trackPageView({path: '/a', referrer: ''});

    window.localStorage.clear();
    await trackPageView({path: '/b', referrer: ''});

    const [first, second] = sentVisitorIds();
    expect(second).toMatch(UUID_V4);
    expect(second).not.toBe(first);
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(second);
  });

  it.each([
    ['empty', ''],
    ['too long', 'a'.repeat(65)],
    ['not URL-safe', 'has spaces and <tags>'],
  ])('replaces a stored value the backend would ignore (%s)', async (_label, stored) => {
    window.localStorage.setItem(STORAGE_KEY, stored);
    const {trackPageView} = await loadAnalytics();

    await trackPageView({path: '/', referrer: ''});

    const [sent] = sentVisitorIds();
    expect(sent).toMatch(UUID_V4);
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(sent);
  });

  it('falls back to one in-memory id per page load when storage cannot be read', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const {trackPageView} = await loadAnalytics();

    await trackPageView({path: '/a', referrer: ''});
    await trackPageView({path: '/b', referrer: ''});

    const [first, second] = sentVisitorIds();
    expect(first).toMatch(UUID_V4);
    expect(second).toBe(first);
    expect(setItem).not.toHaveBeenCalled();
  });

  it('falls back to one in-memory id per page load when storage cannot be written', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    const {trackPageView} = await loadAnalytics();

    await trackPageView({path: '/a', referrer: ''});
    await trackPageView({path: '/b', referrer: ''});

    const [first, second] = sentVisitorIds();
    expect(first).toMatch(UUID_V4);
    expect(second).toBe(first);
    expect(mocks.post).toHaveBeenCalledTimes(2);
  });

  it('still tracks when localStorage does not exist at all', async () => {
    vi.stubGlobal('localStorage', undefined);
    const {trackPageView} = await loadAnalytics();

    await trackPageView({path: '/a', referrer: ''});
    await trackPageView({path: '/b', referrer: ''});

    const [first, second] = sentVisitorIds();
    expect(first).toMatch(UUID_V4);
    expect(second).toBe(first);
  });

  it('builds a version 4 UUID from getRandomValues when randomUUID is missing', async () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.fill(0xff);
      return bytes;
    });
    vi.stubGlobal('crypto', {getRandomValues});
    const {trackPageView} = await loadAnalytics();

    await trackPageView({path: '/', referrer: ''});

    expect(getRandomValues).toHaveBeenCalledTimes(1);
    expect(sentVisitorIds()).toEqual(['ffffffff-ffff-4fff-bfff-ffffffffffff']);
  });

  it('builds a version 4 UUID from Math.random when there is no crypto API', async () => {
    vi.stubGlobal('crypto', undefined);
    const random = vi.spyOn(Math, 'random').mockReturnValue(0);
    const {trackPageView} = await loadAnalytics();

    await trackPageView({path: '/', referrer: ''});

    expect(random).toHaveBeenCalledTimes(16);
    expect(sentVisitorIds()).toEqual(['00000000-0000-4000-8000-000000000000']);
  });

  it('never throws when the request fails', async () => {
    mocks.post.mockRejectedValue(new Error('429'));
    const {trackPageView} = await loadAnalytics();

    await expect(trackPageView({path: '/', referrer: ''})).resolves.toBeUndefined();
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });
});
