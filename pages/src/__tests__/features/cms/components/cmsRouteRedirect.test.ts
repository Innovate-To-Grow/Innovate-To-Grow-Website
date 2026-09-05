import {beforeEach, describe, expect, it, vi} from 'vitest';

import {
  clearCMSRouteRedirectChain,
  performCMSRouteRedirect,
} from '@/features/cms/components/cmsRouteRedirect';

function makeLocation(pathname: string, search = '', hash = '') {
  return {
    origin: 'https://i2g.ucmerced.edu',
    pathname,
    search,
    hash,
    replace: vi.fn(),
  };
}

describe('performCMSRouteRedirect', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('replaces with a same-origin path while preserving query and hash', () => {
    const location = makeLocation('/FAQs', '?partner=1', '#agreements');

    expect(
      performCMSRouteRedirect(
        '/Faqs.v2/~current+page',
        location,
        sessionStorage,
        100,
      ),
    ).toBe('redirected');
    expect(location.replace).toHaveBeenCalledWith(
      '/Faqs.v2/~current+page?partner=1#agreements',
    );
  });

  it.each([
    'https://evil.example/phish',
    '//evil.example/phish',
    '/\\evil.example/phish',
    '/target?replace=1',
    '/target#replace',
    '/safe/%2e%2e/admin',
    '/safe/%2Fadmin',
  ])('rejects unsafe destination %s', (destination) => {
    const location = makeLocation('/old');

    expect(
      performCMSRouteRedirect(destination, location, sessionStorage, 100),
    ).toBe('invalid');
    expect(location.replace).not.toHaveBeenCalled();
  });

  it('treats a trailing-slash-only change as a self redirect', () => {
    const location = makeLocation('/same/');

    expect(
      performCMSRouteRedirect('/same', location, sessionStorage, 100),
    ).toBe('self_redirect');
    expect(location.replace).not.toHaveBeenCalled();
  });

  it('detects a redirect loop across full document loads in the same tab', () => {
    const firstLocation = makeLocation('/old', '?partner=1');
    expect(
      performCMSRouteRedirect('/middle', firstLocation, sessionStorage, 100),
    ).toBe('redirected');

    const secondLocation = makeLocation('/middle', '?partner=1');
    expect(
      performCMSRouteRedirect('/old', secondLocation, sessionStorage, 101),
    ).toBe('redirect_loop');
    expect(secondLocation.replace).not.toHaveBeenCalled();
  });

  it('allows a new redirect chain after a normal page clears the prior chain', () => {
    const firstLocation = makeLocation('/old');
    expect(
      performCMSRouteRedirect('/new', firstLocation, sessionStorage, 100),
    ).toBe('redirected');

    clearCMSRouteRedirectChain();

    const laterLocation = makeLocation('/old');
    expect(
      performCMSRouteRedirect('/new', laterLocation, sessionStorage, 101),
    ).toBe('redirected');
    expect(laterLocation.replace).toHaveBeenCalledWith('/new');
  });

  it('rejects a destination with invalid percent encoding', () => {
    const location = makeLocation('/old');

    expect(
      performCMSRouteRedirect('/target/%zz', location, sessionStorage, 100),
    ).toBe('invalid');
    expect(location.replace).not.toHaveBeenCalled();
  });

  it('redirects without the cross-load loop guard when storage is unavailable', () => {
    const location = makeLocation('/old');

    expect(performCMSRouteRedirect('/new', location, null, 100)).toBe('redirected');
    expect(location.replace).toHaveBeenCalledWith('/new');
  });

  it('returns invalid without touching storage when the destination is unsafe', () => {
    const location = makeLocation('/old');

    expect(
      performCMSRouteRedirect('https://evil.example/phish', location, null, 100),
    ).toBe('invalid');
    expect(location.replace).not.toHaveBeenCalled();
  });

  it('redirects away from the root path', () => {
    const location = makeLocation('/');

    expect(performCMSRouteRedirect('/new', location, sessionStorage, 100)).toBe('redirected');
    expect(location.replace).toHaveBeenCalledWith('/new');
  });

  it('ignores a corrupt redirect chain in storage', () => {
    sessionStorage.setItem('i2g:cms-route-redirect-chain', '{not json');
    const location = makeLocation('/old');

    expect(performCMSRouteRedirect('/new', location, sessionStorage, 100)).toBe('redirected');
    expect(location.replace).toHaveBeenCalledWith('/new');
  });

  it('ignores a stale redirect chain that belongs to another URL', () => {
    sessionStorage.setItem(
      'i2g:cms-route-redirect-chain',
      JSON.stringify({
        expectedHref: '/other',
        visitedPaths: ['/elsewhere'],
        updatedAt: 100,
      }),
    );
    const location = makeLocation('/old');

    expect(performCMSRouteRedirect('/new', location, sessionStorage, 100)).toBe('redirected');
    expect(location.replace).toHaveBeenCalledWith('/new');
  });

  it('ignores a redirect chain that exceeds the maximum age', () => {
    sessionStorage.setItem(
      'i2g:cms-route-redirect-chain',
      JSON.stringify({
        expectedHref: '/old',
        visitedPaths: ['/old'],
        updatedAt: 0,
      }),
    );
    const location = makeLocation('/old');

    expect(
      performCMSRouteRedirect('/new', location, sessionStorage, Date.now() + 60_000),
    ).toBe('redirected');
    expect(location.replace).toHaveBeenCalledWith('/new');
  });

  it('detects a redirect chain that reaches the maximum length', () => {
    const visitedPaths = Array.from({length: 15}, (_, index) => `/step-${index}`);
    sessionStorage.setItem(
      'i2g:cms-route-redirect-chain',
      JSON.stringify({
        expectedHref: '/step-14',
        visitedPaths,
        updatedAt: 100,
      }),
    );
    const location = makeLocation('/step-14');

    expect(performCMSRouteRedirect('/new', location, sessionStorage, 100)).toBe(
      'redirect_loop',
    );
    expect(location.replace).not.toHaveBeenCalled();
  });

  it('clears the chain and rethrows when location.replace fails', () => {
    const location = makeLocation('/old');
    location.replace.mockImplementation(() => {
      throw new Error('navigation blocked');
    });

    expect(() => performCMSRouteRedirect('/new', location, sessionStorage, 100)).toThrow(
      'navigation blocked',
    );
    expect(sessionStorage.getItem('i2g:cms-route-redirect-chain')).toBeNull();
  });

  it('clears the chain without crashing when sessionStorage access throws', () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, 'sessionStorage');
    Object.defineProperty(window, 'sessionStorage', {
      configurable: true,
      get: () => {
        throw new Error('storage disabled');
      },
    });

    try {
      expect(() => clearCMSRouteRedirectChain()).not.toThrow();
    } finally {
      if (descriptor) {
        Object.defineProperty(window, 'sessionStorage', descriptor);
      } else {
        delete (window as {sessionStorage?: Storage}).sessionStorage;
      }
    }
  });
});
