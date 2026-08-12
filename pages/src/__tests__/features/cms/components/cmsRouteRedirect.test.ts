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
});
