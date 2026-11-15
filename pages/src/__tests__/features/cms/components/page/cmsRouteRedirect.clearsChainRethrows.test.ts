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
